-- Pulse · configuración de Supabase (ejecutar UNA vez en el SQL Editor del proyecto,
-- DESPUÉS de `make migrate` y de desplegar en Vercel).
-- Sustituye los dos marcadores <...> antes de ejecutar. No guardes este archivo con
-- valores reales en el repo.

-- 1) Bucket privado para los FIT originales (solo accesible con la service role key).
insert into storage.buckets (id, name, public)
values ('fit', 'fit', false)
on conflict (id) do nothing;

-- 2) Extensiones para la sincronización automática.
create extension if not exists pg_cron;
create extension if not exists pg_net;

-- 3) Secreto compartido con Vercel (mismo valor que CRON_SECRET), guardado en Vault.
select vault.create_secret('<CRON_SECRET>', 'pulse_cron_secret');

-- 4) Cada 10 minutos: avanza la cola de sincronización. El backend decide si toca
--    planificar una sincronización nueva (SYNC_AUTO_INTERVAL_H, 6 h por defecto) o si no
--    hay nada que hacer (respuesta inmediata).
select cron.schedule(
  'pulse-sync-tick',
  '*/10 * * * *',
  $$
  select net.http_post(
    url := 'https://<TU-APP>.vercel.app/api/sync/tick',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'X-Cron-Secret', (select decrypted_secret from vault.decrypted_secrets
                        where name = 'pulse_cron_secret')
    ),
    body := '{}'::jsonb,
    timeout_milliseconds := 60000
  );
  $$
);

-- Comprobar:   select * from cron.job;
--              select * from cron.job_run_details order by start_time desc limit 5;
--              select * from net._http_response order by created desc limit 5;
-- Desactivar:  select cron.unschedule('pulse-sync-tick');
