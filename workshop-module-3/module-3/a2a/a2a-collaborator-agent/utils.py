import boto3


def get_ssm_parameter(name: str, with_decryption: bool = True) -> str:
    """Get parameter from AWS Systems Manager Parameter Store"""
    ssm = boto3.client("ssm")

    response = ssm.get_parameter(Name=name, WithDecryption=with_decryption)

    return response["Parameter"]["Value"]
