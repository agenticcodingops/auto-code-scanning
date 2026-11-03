module "plain" {
  #checkov:skip=CKV_TF_1:Reviewed local module
  source = "./modules/leaf"
}

module "each" {
  #checkov:skip=CKV_TF_1:Reviewed local module
  source = "./modules/leaf"
  for_each = toset(["blue", "green"])
}

module "counted" {
  #checkov:skip=CKV_TF_1:Reviewed local module
  source = "./modules/leaf"
  count = 2
}
