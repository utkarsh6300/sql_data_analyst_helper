import boto3
import json
import os
from botocore.exceptions import ClientError

from dotenv import load_dotenv

load_dotenv()

AWS_BEARER_TOKEN_BEDROCK = os.getenv("AWS_BEARER_TOKEN_BEDROCK")
AWS_BEDROCK_REGION = os.getenv("AWS_BEDROCK_REGION")

class BedrockClient:
    def __init__(self):
        # Set the API key from environment config
        if AWS_BEARER_TOKEN_BEDROCK:
            os.environ["AWS_BEARER_TOKEN_BEDROCK"] = AWS_BEARER_TOKEN_BEDROCK

        # Bedrock runtime for invoke_model and converse
        self.client = boto3.client(
            service_name="bedrock-runtime", region_name=AWS_BEDROCK_REGION
        )

        # Bedrock management operations (e.g., list models)
        self.bedrock = boto3.client(service_name="bedrock", region_name=AWS_BEDROCK_REGION)

    def list_foundation_models(self):
        """List all available foundation models"""
        try:
            response = self.bedrock.list_foundation_models()
            return response.get("modelSummaries", [])
        except ClientError as e:
            raise Exception(f"Failed to list models: {str(e)}")

    def generate_text(
        self,
        prompt=None,
        messages=None,
        model_id=None,
        system_prompts=None,
        temperature=0.5,
        top_p=0.9,
    ):
        """
        Generate text using Bedrock's Converse API
        """
        try:
            if model_id is None:
                raise ValueError("model_id is required")
            if messages is not None:
                # Use provided messages array
                message_list = messages
            elif prompt is not None:
                # Fallback to single user message from prompt
                message_list = [{"role": "user", "content": [{"text": prompt}]}]
            else:
                raise ValueError("Either 'prompt' or 'messages' must be provided")

            # Build the parameters dict conditionally
            params = {
                "modelId": model_id,
                "messages": message_list,
                "inferenceConfig": {
                    "temperature": temperature,
                    "topP": top_p,
                }
            }

            # Only add system if system_prompts exists and is not empty
            if system_prompts:
                params["system"] = system_prompts

            response = self.client.converse(**params)
            return response["output"]["message"]["content"][0]["text"]

        except ClientError as e:
            error_msg = f"Bedrock API error ({e.response['Error']['Code']}): {e.response['Error']['Message']}"
            if "AccessDeniedException" in str(e):
                error_msg += "\nTip: You might need to request model access in AWS console or check your API key"
            raise Exception(error_msg)

    def invoke_model(
        self,
        modelId: str,
        contentType: str = "application/json",
        accept: str = "application/json",
        body: dict = None,
    ):
        """
        Call Bedrock's raw invoke_model endpoint (e.g., for embeddings)

        Parameters:
        modelId (str): Model identifier like 'amazon.titan-embed-text-v1'
        contentType (str): Content-Type of request
        accept (str): Accept type of response
        body (dict): Payload dictionary

        Returns:
        dict: Parsed JSON response
        """
        try:
            response = self.client.invoke_model(
                modelId=modelId,
                contentType=contentType,
                accept=accept,
                body=json.dumps(body),
            )
            return response
        except ClientError as e:
            raise Exception(f"invoke_model failed: {e.response['Error']['Message']}")
        except Exception as e:
            raise Exception(f"Unexpected error during invoke_model: {str(e)}")


# Singleton instance for easy import
bedrock = BedrockClient()
