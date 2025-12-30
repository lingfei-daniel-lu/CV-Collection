# -*- coding: utf-8 -*-
"""
Created on Thu Dec 18 15:20:30 2025

@author: martin
"""



from openai import OpenAI
import os


KIMI_API_KEY = "sk-KrRE2LB9Fph3WP9qdl0zFkhY2e3K7AV7svsspivea58PlJV2"

client = OpenAI(
    api_key=KIMI_API_KEY,
    base_url="https://api.moonshot.ai/v1"
)



print("Testing Kimi API...")

resp = client.models.list()
print(resp)

