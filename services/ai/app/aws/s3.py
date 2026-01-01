import os
import boto3


class S3Client:
    instance = None

    def __init__(self):
        if S3Client.instance._initialized:
            return

        self.access_key_id = os.environ.get("AWS_ACCESS_KEY_ID", None)
        self.secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY", None)

        if not self.access_key_id or not self.secret_access_key:
            raise ValueError("AWS credentials not found")

        self.client = boto3.client(
            "s3",
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
        )

        self._initialized = True

        self.bucket_name = os.environ.get("AWS_BUCKET_NAME", None)
        if not self.bucket_name:
            raise ValueError("AWS bucket name not found")

    def __new__(cls):
        if cls.instance is None:
            cls.instance = super(S3Client, cls).__new__(cls)
            cls.instance._initialized = False
        return cls.instance
    
    def retrieve_object(self, key: str):
        response = self.client.get_object(Bucket=self.bucket_name, Key=key)
        return response["Body"].read()
