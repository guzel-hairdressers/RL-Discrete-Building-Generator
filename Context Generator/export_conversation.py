"""
Export Conversation History Script for Context Generator.
Parses transcript.jsonl and transcript_full.jsonl to export the entire conversation history into a clean text file.
"""

import json
import os
import re

LOG_DIR = "/Users/ruslan_faz/.gemini/antigravity/brain/c88d6b67-d162-4924-b55f-73039b0271dc/.system_generated/logs"
TRANSCRIPT_PATH = os.path.join(LOG_DIR, "transcript.jsonl")
TRANSCRIPT_FULL_PATH = os.path.join(LOG_DIR, "transcript_full.jsonl")
OUTPUT_TXT_PATH = "/Users/ruslan_faz/Desktop/Work/Thesis/Context Generator/Context_Generator_Conversation_History.txt"


def clean_tags(text):
    if not text:
        return ""
    # Strip internal XML wrapper tags if present
    text = re.sub(r"<USER_REQUEST>\s*", "", text)
    text = re.sub(r"\s*</USER_REQUEST>", "", text)
    text = re.sub(r"<ADDITIONAL_METADATA>.*?</ADDITIONAL_METADATA>", "", text, flags=re.DOTALL)
    text = re.sub(r"<USER_SETTINGS_CHANGE>.*?</USER_SETTINGS_CHANGE>", "", text, flags=re.DOTALL)
    return text.strip()


def export_transcript():
    if not os.path.exists(TRANSCRIPT_PATH):
        print(f"Transcript path not found: {TRANSCRIPT_PATH}")
        return

    # Read full transcript lines into lookup dictionary by step_index if needed
    full_lines_by_step = {}
    if os.path.exists(TRANSCRIPT_FULL_PATH):
        with open(TRANSCRIPT_FULL_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    idx = data.get("step_index")
                    if idx is not None:
                        full_lines_by_step[idx] = data
                except Exception:
                    pass

    formatted_entries = []

    with open(TRANSCRIPT_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                idx = data.get("step_index")
                step_type = data.get("type", "")
                source = data.get("source", "")
                
                # Check if truncated
                if data.get("is_truncated") and idx in full_lines_by_step:
                    data = full_lines_by_step[idx]

                content = data.get("content", "")

                if step_type == "USER_INPUT" or source == "USER_EXPLICIT":
                    cleaned_user = clean_tags(content)
                    if cleaned_user:
                        formatted_entries.append(
                            f"\n=================================================================\n"
                            f"USER:\n{cleaned_user}\n"
                            f"=================================================================\n"
                        )

                elif step_type == "PLANNER_RESPONSE" or source == "MODEL":
                    if content and isinstance(content, str):
                        cleaned_resp = content.strip()
                        if cleaned_resp and not cleaned_resp.startswith("Created At"):
                            formatted_entries.append(
                                f"\nANTIGRAVITY ASSISTANT:\n{cleaned_resp}\n"
                            )

            except Exception as e:
                pass

    header = (
        "=================================================================\n"
        "         CONTEXT GENERATOR - FULL CONVERSATION HISTORY           \n"
        "=================================================================\n\n"
    )

    full_text = header + "".join(formatted_entries)

    os.makedirs(os.path.dirname(OUTPUT_TXT_PATH), exist_ok=True)
    with open(OUTPUT_TXT_PATH, "w", encoding="utf-8") as out_f:
        out_f.write(full_text)

    print(f"[Success] Exported complete conversation history to: {OUTPUT_TXT_PATH}")
    print(f"Total formatted conversation turns exported: {len(formatted_entries)}")


if __name__ == "__main__":
    export_transcript()
