module "inner" {
  #checkov:skip=CKV_TF_1:Reviewed local module
  source = "../b"
}
