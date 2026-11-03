module "outer" {
  #checkov:skip=CKV_TF_1:Reviewed local module
  source = "../modules/a"
  for_each = toset(["blue", "green"])
}
