"""Inferencia StockEye v6. Importar este módulo no entrena ni carga pesos.

El modelo y su configuración se cargan una vez mediante cargar_vigente().
No incluye servidor HTTP, endpoints ni listener.
"""
import contextlib, hashlib, json, math, os, shutil, tempfile, time, uuid
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
import cv2
import numpy as np
import psutil
import torch
import torch.nn.functional as F
from transformers import SegformerConfig, SegformerForSemanticSegmentation

PIPELINE_VERSION="stockeye-v6-corregido-1"
FONDO,OCUPADO,VACIO,IGNORAR=0,1,2,255
MEDIA=np.array([.485,.456,.406],np.float32)
DESV=np.array([.229,.224,.225],np.float32)


@dataclass(frozen=True)
class Config:
    semilla: int = 42
    limite_fotos: int | None = None
    frac_dev: float = 0.12
    exigir_series_separadas: bool = True
    exigir_manifest_escenas: bool = False
    usar_externas: bool = True
    modelo_base: str = "nvidia/mit-b1"
    epocas: int = 60
    muestras_por_foto: int = 4
    crop: int = 768
    escala: tuple = (0.7, 1.8)
    prob_centrar_vacio: float = 0.5
    batch: int = 6
    lr: float = 6e-5
    weight_decay: float = 0.01
    eval_cada: int = 5
    paciencia_evals: int = 6
    workers: int = 2
    lado_completa: int = 1280
    tile: int = 640
    solape: float = 0.25
    modos: tuple = ("completa", "tta", "mosaicos", "mosaicos+tta")
    umbrales_vacio: tuple = (0.3, 0.4, 0.5, 0.6)
    tiempo_max_s: float = 5.0
    max_vram_inferencia_gb: float | None = 2.0
    max_vram_entrenamiento_gb: float | None = 4.0
    max_ram_gb: float | None = None
    max_pixeles_imagen: int = 20_000_000
    cierre_frac: float = 0.015
    area_min_gondola: float = 0.01
    cobertura_min_roi: float = 0.80
    area_min_vacio_px: int = 16
    margen_borde_px: int = 3
    iou_emparejar: float = 0.30
    alto_rectificado: int = 800
    repisa_min: float = 0.10
    prominencia_min_bordes: float = 0.005
    stock_verde: float = 70.0
    stock_rojo: float = 30.0
    n_bootstrap: int = 1000
    rangos_vacio: tuple = (0, 10, 30, 70, 100)
    conf_pseudo: float = 0.85
    min_etiquetado: float = 0.60
    min_fotos_reentreno: int = 10
    repetir_nuevas: int = 3
    epocas_reentreno: int = 15
    lr_reentreno: float = 2e-5
    eval_cada_reentreno: int = 3
    repetir_vacias: int = 0
    perdida_recall: bool = False
    tversky_alfa: float = 0.3
    tversky_beta: float = 0.7
    criterio_umbral: str = "iou"
    min_precision: float = 0.40
    franja_min_ancho: float = 0.30
    min_fotos_validacion: int = 10
    min_iou_promocion: float = 0.15
    min_recall_promocion: float = 0.30
    min_recall_alertas_promocion: float = 0.30
    min_cobertura_promocion: float = 0.50
    tolerancia_proporcion: float = 0.01
    tolerancia_mae_pp: float = 0.5
    min_metricas_mejoran: int = 4
    exigir_revision_pseudo: bool = True

def json_seguro(obj):
    if isinstance(obj, dict): return {str(k): json_seguro(v) for k,v in obj.items()}
    if isinstance(obj, (list, tuple)): return [json_seguro(v) for v in obj]
    if isinstance(obj, Path): return str(obj)
    if isinstance(obj, np.ndarray): return json_seguro(obj.tolist())
    if isinstance(obj, np.generic): return json_seguro(obj.item())
    if isinstance(obj, float) and not math.isfinite(obj): return None
    return obj

def json_canonico(obj):
    return json.dumps(json_seguro(obj), ensure_ascii=False, sort_keys=True, separators=(",",":"), allow_nan=False)

def huella_json(obj):
    return hashlib.sha256(json_canonico(obj).encode("utf-8")).hexdigest()

def sha_archivo(ruta):
    h = hashlib.sha256()
    with open(ruta,"rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024*1024), b""): h.update(bloque)
    return h.hexdigest()

def guardar_json(obj, ruta):
    ruta = Path(ruta); ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, temporal = tempfile.mkstemp(prefix=ruta.stem+"_", suffix=".tmp", dir=ruta.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump(json_seguro(obj), f, ensure_ascii=False, indent=2, allow_nan=False)
            f.flush(); os.fsync(f.fileno())
        os.replace(temporal, ruta)
    finally:
        if os.path.exists(temporal): os.unlink(temporal)

def validar_config(cfg):
    for campo in fields(cfg):
        valor=getattr(cfg,campo.name)
        if isinstance(valor,float) and not math.isfinite(valor): raise ValueError("Parámetro no finito: "+campo.name)
    if not (0 <= cfg.stock_rojo < cfg.stock_verde <= 100): raise ValueError("Umbrales de stock inválidos")
    if not 0 <= cfg.solape < 1 or int(cfg.tile*(1-cfg.solape)) < 1: raise ValueError("Mosaicos sin paso válido")
    if cfg.batch < 1 or cfg.epocas < 1 or cfg.crop < 32 or cfg.muestras_por_foto < 1: raise ValueError("Configuración de entrenamiento inválida")
    if not 0 < cfg.area_min_gondola < 1 or not 0 < cfg.repisa_min < 1: raise ValueError("Geometría inválida")
    if not 0<cfg.cobertura_min_roi<=1: raise ValueError("Cobertura mínima de ROI inválida")
    if not 0 < cfg.conf_pseudo <= 1 or not 0 < cfg.min_etiquetado <= 1: raise ValueError("Selección de pseudoetiquetas inválida")
    if any(not 0 < u < 1 for u in cfg.umbrales_vacio): raise ValueError("Umbrales de vacío inválidos")
    if not cfg.modos or set(cfg.modos)-{"completa","tta","mosaicos","mosaicos+tta"}: raise ValueError("Modos de inferencia inválidos")
    if cfg.criterio_umbral not in ("iou","f2"): raise ValueError("Criterio de umbral desconocido")
    if cfg.tiempo_max_s<=0 or cfg.n_bootstrap<1 or cfg.eval_cada<1 or cfg.workers<0: raise ValueError("Límites de ejecución inválidos")
    if cfg.lr<=0 or cfg.lr_reentreno<=0 or len(cfg.escala)!=2 or not 0<cfg.escala[0]<=cfg.escala[1]: raise ValueError("Aprendizaje/escala inválidos")
    if not 0<cfg.frac_dev<1 or not 0<=cfg.min_precision<=1: raise ValueError("Proporción o precisión inválida")
    if cfg.min_fotos_validacion<1 or not 1<=cfg.min_metricas_mejoran<=8 or cfg.tolerancia_proporcion<0 or cfg.tolerancia_mae_pp<0:
        raise ValueError("Compuerta inválida")
    for k in ("max_vram_inferencia_gb","max_vram_entrenamiento_gb","max_ram_gb"):
        if getattr(cfg,k) is not None and getattr(cfg,k)<=0: raise ValueError("Presupuesto de memoria inválido: "+k)
    return cfg

def config_desde_dict(datos):
    conocidos={f.name for f in fields(Config)}
    desconocidos=set(datos)-conocidos
    if desconocidos: raise ValueError(f"Parámetros de otra versión del pipeline: {sorted(desconocidos)}")
    valores=dict(datos)
    for k in ("escala","modos","umbrales_vacio","rangos_vacio"):
        if k in valores: valores[k]=tuple(valores[k])
    return validar_config(Config(**valores))

def leer_imagen(ruta, cfg=None):
    img=cv2.imread(str(ruta),cv2.IMREAD_COLOR)
    if img is None or img.ndim != 3: raise ValueError(f"Imagen ilegible: {ruta}")
    if cfg and img.shape[0]*img.shape[1] > cfg.max_pixeles_imagen:
        raise ValueError(f"Imagen demasiado grande ({img.shape[1]}×{img.shape[0]}). Ajusta explícitamente max_pixeles_imagen.")
    return img

def escribir_imagen(ruta, img):
    ruta=Path(ruta); ruta.parent.mkdir(parents=True,exist_ok=True)
    if not cv2.imwrite(str(ruta),img): raise OSError(f"No se pudo escribir {ruta}")

def dispositivo_de(modelo):
    return next(modelo.parameters()).device

def sincronizar_cuda(modelo=None):
    if torch.cuda.is_available() and (modelo is None or dispositivo_de(modelo).type=="cuda"):
        torch.cuda.synchronize()

def recursos_actuales():
    try: rss=psutil.Process().memory_info().rss
    except (psutil.Error,OSError):
        # Algunos contenedores exponen /proc con un espacio de PID distinto; self mantiene la referencia correcta.
        try: rss=int(Path("/proc/self/statm").read_text().split()[1])*os.sysconf("SC_PAGE_SIZE")
        except (OSError,ValueError,IndexError) as error: raise RuntimeError("No se pudo medir la memoria del proceso") from error
    return dict(ram_gb=rss/1024**3,
                vram_gb=torch.cuda.max_memory_allocated()/1024**3 if torch.cuda.is_available() else 0.0)

def comprobar_recursos(cfg, entrenamiento=False):
    r=recursos_actuales()
    limite=cfg.max_vram_entrenamiento_gb if entrenamiento else cfg.max_vram_inferencia_gb
    if limite is not None and r["vram_gb"] > limite:
        raise RuntimeError(f"VRAM {r['vram_gb']:.2f} GB > {limite} GB. Reduce batch/crop o cambia la configuración y crea otra ejecución.")
    if cfg.max_ram_gb is not None and r["ram_gb"] > cfg.max_ram_gb: raise RuntimeError("Se excedió el límite de RAM")
    return r

def rellenar(puntos,H,W):
    puntos=np.asarray(puntos,float)
    if H<1 or W<1 or puntos.ndim!=2 or puntos.shape[1]!=2 or len(puntos)<3 or not np.isfinite(puntos).all():
        raise ValueError("Polígono o dimensiones inválidos")
    m=np.zeros((H,W),np.uint8)
    cv2.fillPoly(m,[np.round(puntos).astype(np.int32)],1)
    return m.astype(bool)

def a_tensor(img_bgr):
    rgb=img_bgr[...,::-1].astype(np.float32)/255
    return torch.from_numpy(((rgb-MEDIA)/DESV).transpose(2,0,1).copy())

@torch.inference_mode()
def probabilidad(modelo,img,lado):
    h,w=img.shape[:2];escala=lado/max(h,w)
    nh,nw=max(32,round(h*escala/32)*32),max(32,round(w*escala/32)*32)
    device=dispositivo_de(modelo)
    x=a_tensor(cv2.resize(img,(nw,nh),interpolation=cv2.INTER_LINEAR)).unsqueeze(0).to(device)
    with torch.autocast(device_type=device.type,enabled=device.type=="cuda"):
        logits=modelo(pixel_values=x).logits
    return F.interpolate(logits.float(),size=(h,w),mode="bilinear",align_corners=False).softmax(1)[0].cpu().numpy()

class Segmentador(Protocol):
    def mapa(self,img: np.ndarray) -> np.ndarray: ...

def mapa_desde_prob(p,umbral):
    if p.ndim!=3 or p.shape[0]!=3 or not np.isfinite(p).all(): raise ValueError("Probabilidades inválidas")
    if not 0<umbral<1: raise ValueError("Umbral fuera de rango")
    m=(p[OCUPADO]>p[FONDO]).astype(np.uint8)
    m[p[VACIO]>=umbral]=VACIO
    return m

def ventanas(lado,tile,solape):
    paso=int(tile*(1-solape))
    if lado<1 or tile<1 or paso<1: raise ValueError("Ventanas inválidas")
    return [0] if lado<=tile else sorted(set(list(range(0,lado-tile,paso))+[lado-tile]))

class SegmentadorSegFormer:
    def __init__(self,modelo,cfg,modo="completa",umbral=0.5):
        validar_config(cfg)
        if modo not in cfg.modos: raise ValueError("Modo desconocido")
        self.modelo,self.cfg,self.modo,self.umbral=modelo.eval(),cfg,modo,float(umbral)
    def _sin_tta(self,img):
        p=probabilidad(self.modelo,img,self.cfg.lado_completa)
        if "mosaicos" not in self.modo: return p
        h,w=img.shape[:2];suma=p.copy();peso=np.ones((h,w),np.float32)
        for y in ventanas(h,self.cfg.tile,self.cfg.solape):
            for x in ventanas(w,self.cfg.tile,self.cfg.solape):
                r=img[y:y+self.cfg.tile,x:x+self.cfg.tile]
                suma[:,y:y+r.shape[0],x:x+r.shape[1]]+=probabilidad(self.modelo,r,self.cfg.crop)
                peso[y:y+r.shape[0],x:x+r.shape[1]]+=1
        return suma/peso
    def prob(self,img):
        p=self._sin_tta(img)
        if "tta" in self.modo: p=(p+self._sin_tta(img[:,::-1])[:,:,::-1])/2
        return p
    def mapa(self,img): return mapa_desde_prob(self.prob(img),self.umbral)

def cargar_segformer(ruta,cfg,device=None,model_config=None):
    c=torch.load(ruta,map_location="cpu",weights_only=True)
    if "modelo" not in c: raise ValueError("No es un checkpoint SegFormer de StockEye")
    arquitectura=model_config or c.get("model_config")
    if arquitectura is None:
        base=c.get("config",{}).get("modelo_base")
        if base!=cfg.modelo_base: raise ValueError("El modelo base del checkpoint antiguo no coincide con la configuración")
        # Importación explícita de pesos antiguos para reevaluar. Solo aquí puede necesitarse la configuración de HF.
        hfcfg=SegformerConfig.from_pretrained(base)
        hfcfg.num_labels=3;hfcfg.id2label={0:"fondo",1:"ocupado",2:"vacio"};hfcfg.label2id={v:k for k,v in hfcfg.id2label.items()}
    else:
        hfcfg=SegformerConfig.from_dict(arquitectura)
    if hfcfg.num_labels!=3: raise ValueError("El checkpoint no tiene las tres clases esperadas")
    modelo=SegformerForSemanticSegmentation(hfcfg)
    modelo.load_state_dict(c["modelo"],strict=True)
    modelo.stockeye_sha256=sha_archivo(ruta)
    return modelo.to(device or ("cuda" if torch.cuda.is_available() else "cpu")).eval()

def cuadrilatero(m):
    cnts,_=cv2.findContours(m.astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    if not cnts: raise ValueError("Región vacía")
    p=cv2.convexHull(np.vstack(cnts)).reshape(-1,2).astype(np.float32)
    s,d=p.sum(1),p[:,0]-p[:,1]
    q=np.array([p[s.argmin()],p[d.argmax()],p[s.argmax()],p[d.argmin()]],np.float32)
    triangulos=[cv2.contourArea(q[[i,(i+1)%4,(i+2)%4]]) for i in range(4)]
    if min(triangulos)>=.05*max(cv2.contourArea(p),1): return q
    c,(w,h),angulo=cv2.minAreaRect(p)
    r=cv2.boxPoints((c,(max(w,2.),max(h,2.)),angulo)).astype(np.float32)
    r=r[np.argsort(np.arctan2(r[:,1]-c[1],r[:,0]-c[0]))]
    return np.roll(r,-int(r.sum(1).argmin()),axis=0)

def homografia(q,alto):
    q=np.asarray(q,np.float32)
    if q.shape!=(4,2) or not np.isfinite(q).all(): raise ValueError("Cuadrilátero inválido")
    ancho=(np.linalg.norm(q[1]-q[0])+np.linalg.norm(q[2]-q[3]))/2
    alto_q=(np.linalg.norm(q[3]-q[0])+np.linalg.norm(q[2]-q[1]))/2
    w=int(np.clip(round(alto*ancho/max(alto_q,1)),32,2400))
    M=cv2.getPerspectiveTransform(q,np.array([[0,0],[w,0],[w,alto],[0,alto]],np.float32))
    if not np.isfinite(M).all() or abs(np.linalg.det(M))<1e-12: raise ValueError("Perspectiva degenerada")
    return M,w

def pct_rectificado(region,vacio,q,alto):
    M,w=homografia(q,alto)
    r=cv2.warpPerspective(region.astype(np.uint8),M,(w,alto),flags=cv2.INTER_NEAREST)>0
    v=cv2.warpPerspective((vacio&region).astype(np.uint8),M,(w,alto),flags=cv2.INTER_NEAREST)>0
    return 100*np.count_nonzero(v)/np.count_nonzero(r) if r.any() else None

def cortar_repisas(img,q,alto,repisa_min,prominencia_min=0.005):
    M,w=homografia(q,alto)
    g=cv2.cvtColor(cv2.warpPerspective(img,M,(w,alto)),cv2.COLOR_BGR2GRAY).astype(np.float32)
    gy,gx=np.abs(cv2.Sobel(g,cv2.CV_32F,0,1,ksize=3)),np.abs(cv2.Sobel(g,cv2.CV_32F,1,0,ksize=3))
    perfil=((gy>2*gx)&(gy>np.percentile(gy,75)))[:,int(.1*w):max(int(.1*w)+1,int(.9*w))].mean(1)
    s=max(1.,.006*alto);xx=np.arange(-int(3*s),int(3*s)+1)
    k=np.exp(-.5*(xx/s)**2);perfil=np.convolve(perfil,k/k.sum(),mode="same")
    amplitud=float(np.ptp(perfil));cortes=[]
    if amplitud>=prominencia_min:
        umbral=float(np.median(perfil))+max(.25*amplitud,prominencia_min)
        activos=np.nonzero((perfil>umbral)&(np.arange(alto)>.03*alto)&(np.arange(alto)<.97*alto))[0]
        grupos=np.split(activos,np.where(np.diff(activos)>1)[0]+1) if len(activos) else []
        candidatos=[]
        for grupo in grupos:
            if not len(grupo): continue
            maximo=perfil[grupo].max();meseta=grupo[np.isclose(perfil[grupo],maximo,rtol=1e-4,atol=1e-8)]
            candidatos.append(int(meseta[len(meseta)//2]))
        for i in sorted(candidatos,key=lambda i:-perfil[i]):
            if all(abs(i-j)>=repisa_min*alto for j in cortes): cortes.append(i)
    ys=[0]+sorted(cortes)+[alto];Minv=np.linalg.inv(M)
    return [cv2.perspectiveTransform(np.array([[[0,a],[w,a],[w,b],[0,b]]],np.float32),Minv)[0] for a,b in zip(ys,ys[1:])]

def semaforo(pct,cfg):
    if pct is None or not math.isfinite(float(pct)) or not 0<=pct<=100: return "indeterminado"
    stock=100-float(pct)
    return "verde" if stock>=cfg.stock_verde else "rojo" if stock<cfg.stock_rojo else "amarillo"

def franja_continua(vacio,region):
    n,_,stats,_=cv2.connectedComponentsWithStats((vacio&region).astype(np.uint8))
    if n<2 or not region.any(): return 0.
    xs=np.nonzero(region)[1]
    return float(stats[1:,cv2.CC_STAT_WIDTH].max()/max(1,xs.max()-xs.min()+1))

def semaforo_prudente(g,rep,vacio,cfg):
    # Una región parcial no representa la ocupación del mueble completo.
    if g["parcial"]: return "revisar"
    color=semaforo(g["pct"],cfg)
    if rep["confiable"] and any(semaforo(r["pct"],cfg)=="rojo" for r in rep["repisas"]): return "rojo"
    if color=="verde" and not rep["confiable"] and franja_continua(vacio,g["region"])>=cfg.franja_min_ancho: return "revisar"
    return color

def gondolas_desde_mapa(mapa,cfg,rois=None):
    if mapa.ndim!=2 or not set(np.unique(mapa))<={FONDO,OCUPADO,VACIO}: raise ValueError("Mapa de clases inválido")
    H,W=mapa.shape;salida=[];base=(mapa==OCUPADO)|(mapa==VACIO);vacio=mapa==VACIO
    regiones=[]
    if rois:
        ids=[r.get("gondola_id") for r in rois]
        if any(not isinstance(gid,str) or not gid for gid in ids) or len(ids)!=len(set(ids)):
            raise ValueError("Cada ROI calibrada requiere un gondola_id único")
        ocupada=np.zeros_like(base)
        for roi in rois:
            q=np.asarray(roi["poligono"],float)
            if roi.get("normalizada",True) and (not np.isfinite(q).all() or q.min()<0 or q.max()>1):
                raise ValueError("ROI normalizada fuera de [0,1]")
            if roi.get("normalizada",True): q=q*np.array([W-1,H-1])
            region=rellenar(q,H,W)
            if (region&ocupada).any(): raise ValueError("Las ROI de góndolas se superponen")
            ocupada|=region
            regiones.append((region,roi.get("gondola_id"),True))
    else:
        n,labels=cv2.connectedComponents(base.astype(np.uint8))
        regiones=[(labels==i,None,False) for i in range(1,n)]
    k=max(3,int(cfg.cierre_frac*max(H,W)))|1
    for region,gid,calibrada in regiones:
        if np.count_nonzero(region)<cfg.area_min_gondola*H*W: continue
        # El cierre se usa para forma, por componente; no fusiona góndolas ni inventa píxeles ocupados en el denominador.
        forma=cv2.morphologyEx(region.astype(np.uint8),cv2.MORPH_CLOSE,np.ones((k,k),np.uint8))>0
        q=cuadrilatero(forma);ys,xs=np.nonzero(region);b=cfg.margen_borde_px
        parcial=not calibrada and (xs.min()<=b or ys.min()<=b or xs.max()>=W-1-b or ys.max()>=H-1-b)
        evidencia=region&base
        if not evidencia.any(): continue
        cobertura=float(np.count_nonzero(evidencia)/np.count_nonzero(region))
        if calibrada and cobertura<cfg.cobertura_min_roi: parcial=True
        pct=100*np.count_nonzero(vacio&evidencia)/np.count_nonzero(evidencia)
        n,_,stats,_=cv2.connectedComponentsWithStats((vacio&region).astype(np.uint8))
        cantidad=int(sum(area>=cfg.area_min_vacio_px for area in stats[1:,cv2.CC_STAT_AREA])) if n>1 else 0
        salida.append(dict(region=evidencia,q=q,parcial=bool(parcial),pct=pct,
                           pct_rect=pct_rectificado(evidencia,vacio,q,cfg.alto_rectificado),gondola_id=gid,
                           cantidad_regiones_vacias=cantidad,roi_calibrada=calibrada,cobertura_roi=cobertura if calibrada else None))
    return salida

def repisas_de(img,g,vacio,cfg):
    bandas=cortar_repisas(img,g["q"],cfg.alto_rectificado,cfg.repisa_min,cfg.prominencia_min_bordes)
    H,W=vacio.shape;filas=[]
    for b in bandas:
        r=rellenar(b,H,W)&g["region"]
        if r.any():
            filas.append(dict(cuadrilatero=b.round(2).tolist(),pct=100*np.count_nonzero(vacio&r)/np.count_nonzero(r),area=int(np.count_nonzero(r))))
    areas=[r["area"] for r in filas]
    confiable=len(filas)>=2 and min(areas)/max(areas)>=.25
    motivo="bordes_y_areas_validos" if confiable else "sin_cortes_con_evidencia" if len(filas)<2 else "areas_desiguales"
    return dict(confiable=bool(confiable),motivo=motivo,repisas=filas)

def postprocesar_mapa(img,mapa,cfg,rois=None):
    vacio=mapa==VACIO;salida=[]
    for i,g in enumerate(gondolas_desde_mapa(mapa,cfg,rois),1):
        rep=repisas_de(img,g,vacio,cfg);color=semaforo_prudente(g,rep,vacio,cfg)
        salida.append(dict(id_local=i,gondola_id=g["gondola_id"],estado="parcial" if g["parcial"] else "medida",
                           pct_vacio_observado=round(g["pct"],2),pct_vacio_gondola_completa=None if g["parcial"] else round(g["pct"],2),
                           pct_vacio_rectificado=None if g["pct_rect"] is None else round(g["pct_rect"],2),semaforo=color,alerta=color=="rojo",
                           cantidad_regiones_vacias=g["cantidad_regiones_vacias"],unidad_conteo="regiones_conexas_no_instancias",
                           cobertura_roi=g["cobertura_roi"],
                           cuadrilatero=g["q"].round(2).tolist(),repisas_confiables=rep["confiable"],motivo_repisas=rep["motivo"],
                           repisas=[dict(numero=j,pct=round(r["pct"],2),area=r["area"],cuadrilatero=r["cuadrilatero"],semaforo="revisar" if g["parcial"] else semaforo(r["pct"],cfg)) for j,r in enumerate(rep["repisas"],1)] if rep["confiable"] else []))
    return salida

def leer_versiones(carpeta):
    ruta=Path(carpeta)/"versiones.json"
    if not ruta.exists(): return []
    doc=json.loads(ruta.read_text())
    if not isinstance(doc,list) or any(r.get("esquema")!="stockeye-registro-2" for r in doc):
        raise ValueError("Registro incompatible; utiliza la carpeta corregido_v1/modelos")
    return doc

def comprobar_bundle(carpeta,bundle_id):
    carpeta=Path(carpeta);m=json.loads((carpeta/"manifest.json").read_text())
    if m.get("esquema")!="stockeye-bundle-1" or m.get("bundle_id")!=bundle_id or huella_json(m.get("identidad"))!=bundle_id:
        raise ValueError("Identidad del bundle inválida")
    if m["identidad"].get("pipeline")!=PIPELINE_VERSION: raise ValueError("Versión del pipeline incompatible")
    for nombre in ("weights.pt","model_config.json"):
        if sha_archivo(carpeta/nombre)!=m.get("archivos",{}).get(nombre): raise ValueError("Archivo de modelo alterado: "+nombre)
    return m

@dataclass(frozen=True)
class ContextoInferencia:
    segmentador: SegmentadorSegFormer
    cfg: Config
    version: str
    bundle_id: str
    carpeta_bundle: Path
    promovido: bool=True

def cargar_vigente(carpeta_modelos,device=None):
    carpeta=Path(carpeta_modelos);reg=leer_versiones(carpeta)
    aprobados=[r for r in reg if r["promovido"]]
    if not aprobados: raise FileNotFoundError("Aún no hay un modelo promovido que cumpla la compuerta")
    r=aprobados[-1];bundle=carpeta/"bundles"/r["bundle_id"]
    manifest=comprobar_bundle(bundle,r["bundle_id"]);identidad=manifest["identidad"]
    cfg=config_desde_dict(identidad["config"])
    modelo=cargar_segformer(bundle/"weights.pt",cfg,device=device,model_config=json.loads((bundle/"model_config.json").read_text()))
    seg=SegmentadorSegFormer(modelo,cfg,identidad["modo"],identidad["umbral"])
    return ContextoInferencia(seg,cfg,r["version"],r["bundle_id"],bundle)

def fecha_utc(valor=None):
    fecha=datetime.now(timezone.utc) if valor is None else datetime.fromisoformat(str(valor).replace("Z","+00:00"))
    if fecha.tzinfo is None: raise ValueError("La fecha debe incluir zona horaria, por ejemplo 2026-10-31T12:00:00-03:00")
    return fecha.astimezone(timezone.utc).isoformat()

def analizar_foto(ruta,contexto,*,captura_id=None,capturada_en=None,sucursal_id=None,camara_id=None,rois=None,con_probabilidades=False):
    if not isinstance(contexto,ContextoInferencia) or not contexto.promovido:
        raise ValueError("La inferencia operativa requiere el contexto de un modelo promovido")
    cfg=contexto.cfg;seg=contexto.segmentador;ruta=Path(ruta)
    if torch.cuda.is_available(): torch.cuda.reset_peak_memory_stats()
    sincronizar_cuda(seg.modelo);t0=time.perf_counter()
    img=leer_imagen(ruta,cfg);p=seg.prob(img);mapa=mapa_desde_prob(p,seg.umbral)
    gondolas=postprocesar_mapa(img,mapa,cfg,rois)
    sincronizar_cuda(seg.modelo);segundos=time.perf_counter()-t0;recursos=comprobar_recursos(cfg)
    if segundos>cfg.tiempo_max_s:
        raise TimeoutError(f"La inferencia tardó {segundos:.2f}s; presupuesto {cfg.tiempo_max_s}s. Ajusta el modo y vuelve a validarlo.")
    h,w=img.shape[:2]
    estado="sin_gondola" if not gondolas else "parcial" if any(g["estado"]=="parcial" for g in gondolas) else "medida"
    resultado=dict(esquema="stockeye-resultado-1",analisis_id=uuid.uuid4().hex,captura_id=str(captura_id or uuid.uuid4().hex),
                   foto=ruta.name,sha256_original=sha_archivo(ruta),fecha_analisis=fecha_utc(),
                   capturada_en=fecha_utc(capturada_en) if capturada_en is not None else None,
                   sucursal_id=sucursal_id,camara_id=camara_id,estado_proceso="completado",estado_medicion=estado,
                   version_modelo=contexto.version,bundle_id=contexto.bundle_id,pipeline=PIPELINE_VERSION,
                   operacion=dict(modo=seg.modo,umbral_vacio=seg.umbral),
                   dimensiones=dict(original=dict(ancho=w,alto=h),mapa=dict(ancho=w,alto=h)),
                   coordenadas="pixeles_de_imagen_original_decodificada_con_orientacion_exif",
                   segundos=round(segundos,4),alcance_tiempo="lectura_prediccion_geometria_sin_red_ni_guardado",recursos=recursos,
                   cantidad_gondolas_detectadas=len(gondolas),
                   unidad_gondola="roi_calibrada" if rois else "componente_semantico_sin_identidad_fisica",
                   cantidad_regiones_vacias=sum(g["cantidad_regiones_vacias"] for g in gondolas),gondolas=gondolas)
    return (resultado,mapa,p) if con_probabilidades else (resultado,mapa)

def guardar_analisis(ruta,resultado,mapa,carpeta):
    ruta=Path(ruta);carpeta=Path(carpeta);carpeta.mkdir(parents=True,exist_ok=True)
    if sha_archivo(ruta)!=resultado["sha256_original"]: raise ValueError("La foto cambió entre el análisis y el guardado")
    img=leer_imagen(ruta)
    if img.shape[:2]!=mapa.shape: raise ValueError("La máscara no corresponde a las dimensiones de la foto")
    destino=carpeta/resultado["analisis_id"]
    if destino.exists(): raise FileExistsError("Ese análisis ya existe; no se sobrescribe")
    temporal=Path(tempfile.mkdtemp(prefix=".analisis_",dir=carpeta))
    try:
        extension=ruta.suffix.lower() if ruta.suffix.lower() in (".jpg",".jpeg",".png",".webp",".bmp",".tif",".tiff") else ".img"
        original="original"+extension
        shutil.copyfile(ruta,temporal/original)
        escribir_imagen(temporal/"mascara.png",mapa.astype(np.uint8))
        escribir_imagen(temporal/"superpuesta.jpg",pintar(img,mapa))
        documento=dict(resultado)
        documento["archivos"]={"original":original,"mascara":"mascara.png","superpuesta":"superpuesta.jpg","resultado":"resultado.json"}
        documento["sha256_archivos"]={n:sha_archivo(temporal/n) for n in (original,"mascara.png","superpuesta.jpg")}
        guardar_json(documento,temporal/"resultado.json")
        temporal.rename(destino)
    finally:
        if temporal.exists(): shutil.rmtree(temporal)
    return destino

def pintar(img: np.ndarray, m: np.ndarray) -> np.ndarray:
    salida = img.copy()
    salida[m == OCUPADO] = 0.65 * salida[m == OCUPADO] + 0.35 * np.array([246, 130, 59])
    salida[m == VACIO] = 0.45 * salida[m == VACIO] + 0.55 * np.array([0, 204, 250])
    return salida

def main():
    import argparse
    p=argparse.ArgumentParser(description="Analizar una imagen con un modelo StockEye aprobado")
    p.add_argument("--modelos",required=True,type=Path)
    p.add_argument("--imagen",required=True,type=Path)
    p.add_argument("--salida",required=True,type=Path)
    p.add_argument("--device",choices=("cpu","cuda"),default=None)
    args=p.parse_args()
    contexto=cargar_vigente(args.modelos,device=args.device)
    resultado,mapa=analizar_foto(args.imagen,contexto)
    destino=guardar_analisis(args.imagen,resultado,mapa,args.salida)
    print(json.dumps({"analisis_id":resultado["analisis_id"],"carpeta":str(destino)},ensure_ascii=False))

if __name__=="__main__":
    main()
