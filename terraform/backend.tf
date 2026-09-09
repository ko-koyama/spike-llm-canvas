# Terraform本体とAWSプロバイダのバージョン制約、tfstateの保存先を定義する
terraform {
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket = "spike-llm-canvas-viz-tfstate"
    key    = "spike-llm-canvas-viz/terraform.tfstate"
    region = "ap-northeast-1"
  }
}

# リソースの作成先リージョンを指定する
provider "aws" {
  region = "ap-northeast-1"
}
