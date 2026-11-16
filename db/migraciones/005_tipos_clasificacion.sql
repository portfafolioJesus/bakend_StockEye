-- Valores nuevos: deben confirmarse antes de utilizarlos en la migración 006.
BEGIN;
ALTER TYPE tipo_tarea ADD VALUE IF NOT EXISTS 'CLASIFICAR_IMAGEN';
ALTER TYPE tipo_notificacion ADD VALUE IF NOT EXISTS 'IA_CUOTA';
COMMIT;
