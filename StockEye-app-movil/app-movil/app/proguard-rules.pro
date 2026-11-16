# Reglas de ProGuard (vacío por ahora)

# kotlinx.serialization (modelos de la API)
-keepattributes *Annotation*, InnerClasses
-keepclassmembers @kotlinx.serialization.Serializable class cl.duoc.stockeye.data.** {
    *** Companion;
    kotlinx.serialization.KSerializer serializer(...);
}
-keep,includedescriptorclasses class cl.duoc.stockeye.data.**$$serializer { *; }
# Retrofit usa reflexión sobre las interfaces con anotaciones
-keep,allowobfuscation interface cl.duoc.stockeye.data.StockEyeApi
-keepattributes Signature, Exceptions
