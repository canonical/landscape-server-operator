landscape_server = {
  channel = "26.04/stable"
  config = {
    autoregistration               = "true"
    landscape_ppa                  = "ppa:landscape/self-hosted-26.04"
    root_url                       = "https://landscape.local/"
    enable_hostagent_messenger     = "true"
    enable_ubuntu_installer_attach = "true"
    outbox_snap_channel            = "latest/stable"
  }
  base = "ubuntu@24.04"
}

postgresql = {
  channel = "16/stable"
  base    = "ubuntu@24.04"
}

pgbouncer = {
  channel = "1/stable"
  base    = "ubuntu@24.04"
}

haproxy = {
  channel = "2.8/stable"
  base    = "ubuntu@24.04"
  config  = {}
}

landscape_debarchive = {
  channel = "latest/stable"
  base    = "ubuntu@24.04"
}

landscape_task_handler = {
  channel = "latest/stable"
  base    = "ubuntu@24.04"
}
