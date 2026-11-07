import boto3
import os
from botocore.exceptions import NoCredentialsError


def get_r2_client():
    try:
        return boto3.client(
            "s3",
            endpoint_url=os.getenv("R2_ENDPOINT_URL"),
            aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
            region_name="auto",
        )
    except Exception as e:
        print(f"Error creating R2 client: {e}")
        return None


def upload_file_to_r2(file_path: str, object_name: str) -> str:
    """
    Uploads a file to R2 and returns the public URL.
    """
    r2 = get_r2_client()
    if not r2:
        return ""

    try:
        bucket_name = os.getenv("R2_BUCKET_NAME")
        r2.upload_file(file_path, bucket_name, object_name)
        public_url_base = os.getenv("R2_MEDIA_URL")
        if not public_url_base:
            print("Warning: R2_MEDIA_URL not set")
            return ""

        public_url = f"{public_url_base}/{object_name}"
        return public_url
    except FileNotFoundError:
        print(f"ERROR: The file {file_path} was not found")
        return ""
    except NoCredentialsError:
        print("ERROR: Credentials not available for R2")
        return ""
    except Exception as e:
        print(f"ERROR uploading to R2: {e}")
        import traceback

        traceback.print_exc()
        return ""
