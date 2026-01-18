import boto3
from botocore.exceptions import ClientError


def get_ssm_parameter(name: str, with_decryption: bool = True) -> str:
    try:
        ssm = boto3.client("ssm")
        response = ssm.get_parameter(Name=name, WithDecryption=with_decryption)
        return response["Parameter"]["Value"]
    except ClientError as e:
        if e.response['Error']['Code'] == 'ParameterNotFound':
            return None
        raise
