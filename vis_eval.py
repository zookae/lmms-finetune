import os
os.environ["WANDB_PROJECT"]= "lmms-ft"
from dataclasses import asdict
import logging
from pathlib import Path
from typing import List
import yaml
import gc
from accelerate.utils import DistributedType
import torch
import transformers
from transformers import Trainer, deepspeed

# from arguments import ModelArguments, DataArguments, TrainingArguments, LoraArguments
# from collators import COLLATORS
# from datasets import LazySupervisedDataset
# from loaders import LOADERS
from conversation import conv_templates, SeparatorStyle
# from lmms_utils import (
#     rank0_print, find_all_linear_names, safe_save_model_for_hf_trainer,
#     get_peft_state_maybe_zero_3, MULTIMODAL_KEYWORDS
# )
from PIL import Image
import requests
import json

import base64
from openai import OpenAI
# Initializing OpenAI client - see https://platform.openai.com/docs/quickstart?context=python
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

client = OpenAI()
def get_gpt4o_response(conversation):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=conversation,
    )
    return response.choices[0].message.content

def convert_json_format(data, for_gpt4o=False):
    conversation = []
    
    for conv in data['conversations']:
        if conv['from'] == 'human':
            user_content = [
                {
                    "type": "text",
                    "text": conv['value'].replace("<image>", "")
                }
            ]
            if for_gpt4o:
                for i in range(conv['value'].count("<image>")):
                    encoded_image = encode_image(data['image'][i])
                    user_content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{encoded_image}"}
                        }
                    )
            else:
                user_content.extend([{"type": "image"} for _ in range(conv['value'].count("<image>"))])
            
            conversation.append({
                "role": "user",
                "content": user_content
            })
    image_list = [Image.open(image_path).convert("RGB") for image_path in data["image"]]
    return conversation, image_list

def eval():
    # parser = transformers.HfArgumentParser(
    #     (ModelArguments, DataArguments, TrainingArguments, LoraArguments)
    # )
    # model_args, data_args, training_args, lora_args = parser.parse_args_into_dataclasses()
    # dumping arguments
    from transformers import AutoProcessor, LlavaForConditionalGeneration
    test_input_file_path = '/viscam/projects/GenLayout/GenLayout_sun/data/3dfront_data/v6/llava_before_refine_test.json'
    test_input_file_path = '/viscam/projects/GenLayout/GenLayout_sun/data/synthetic_data/v0/perception_task.json'

    original_model_id = "llava-hf/llava-interleave-qwen-7b-hf"
    #################### test original
    model_id = original_model_id
    #################### test finetuned
    _folder = 'llava-interleave-qwen-7b_v6-llava_before_refine_train_v6-llava_before_refine_test_lora-True_qlora-False_vision-False_visionlora-False'
    _checkpoint_id = 'checkpoint-800'
    model_id = f'/viscam/projects/GenLayout/GenLayout_sun/third_party/lmms-finetune/checkpoints/{_folder}/{_checkpoint_id}'
    print(model_id)

    model = LlavaForConditionalGeneration.from_pretrained(
        model_id, #model_id
        torch_dtype=torch.float16, 
        #low_cpu_mem_usage=True, 
    ).to(0)
    # processor is not changed so we still load from the original model repo
    processor = AutoProcessor.from_pretrained(original_model_id)
    tokenizer = processor.tokenizer
    tokenizer.model_max_length = 4096 

    with open(test_input_file_path, 'r') as f:
        data = json.load(f)

    for i in range(len(data)):
        entry = data[i]
        conversation, image_list = convert_json_format(entry)
        gpt_conversation, _ = convert_json_format(entry, for_gpt4o=True)
        prompt = processor.apply_chat_template(conversation, add_generation_prompt=True)
        inputs = processor(prompt, image_list, return_tensors='pt').to(0, torch.float16)
        print(inputs['input_ids'].shape, inputs['attention_mask'].shape, inputs['pixel_values'].shape)
        #if inputs['pixel_values'].shape[1] > tokenizer.model_max_length:
        #    import pdb;pdb.set_trace()
        #continue

        outputs = model.generate(
            **inputs,
            max_new_tokens=2048,
            do_sample=True,
            # return_dict_in_generate=True,
            # output_attentions=False
        )

        decoded_output = processor.decode(outputs[0][2:], skip_special_tokens=True)
        # Find the position where "assistant\n" starts in the decoded output
        start_position = decoded_output.find("assistant\n")
        # Print the output starting from "assistant\n"
        if start_position != -1:
            print("------job id-----------", flush=True)
            print(entry["id"], flush=True)
            print("------model output-----------", flush=True)
            print(decoded_output[start_position:], flush=True)

        print("------ground truth-----------", flush=True)
        print(entry["conversations"][1]['value'], flush=True)
        print("------gpt-4o ----------------", flush=True)
        print(get_gpt4o_response(gpt_conversation), flush=True)
        print('###################################################################')
        print('###################################################################')




if __name__ == "__main__":
    eval()