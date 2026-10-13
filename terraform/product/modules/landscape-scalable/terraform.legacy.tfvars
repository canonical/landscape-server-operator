// Legacy deployment (24.04)
landscape_server = {
  channel = "24.04/stable"
  base    = "ubuntu@24.04"
  config = {
    landscape_ppa = "ppa:landscape/self-hosted-24.04"
  }
}

haproxy = {
  channel = "latest/stable"
  config = {
    default_timeouts            = "queue 60000, connect 5000, client 120000, server 120000"
    services                    = ""
    ssl_cert                    = "SELFSIGNED"
    global_default_bind_options = "no-tlsv10"
  }
}

postgresql = {
  channel = "14/stable"
  base    = "ubuntu@22.04"
}

landscape_debarchive   = null
landscape_task_handler = null
pgbouncer              = null
