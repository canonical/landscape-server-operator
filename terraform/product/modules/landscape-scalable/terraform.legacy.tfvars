// Legacy deployment (24.04)
landscape_server = {
  channel = "24.04/stable"
  base    = "ubuntu@24.04"
  config = {
    landscape_ppa = "ppa:landscape/self-hosted-24.04"
  }
}

landscape_debarchive   = null
landscape_task_handler = null
