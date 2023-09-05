import os
import re
from datetime import datetime

directory = "test_logs/qrm_logs"

file_pattern = re.compile(r'qrm_server\.txt\.\d{4}-\d{2}-\d{2}$')
new_token_pattern = re.compile(
    r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\].*\[new request.*'tags': (\[.*?\]), 'token': '([^']+)'")
tag_pattern = re.compile(r"'tags': \['([^']+)'\], 'count': (\d+)")
filled_token_pattern = re.compile(
    r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\].*\[fill for token ([^\s]+) is.*token='([^']+)'.*\]")

token_info = {}
filled_tokens = {}

for filename in os.listdir(directory):
    if file_pattern.match(filename):
        with open(os.path.join(directory, filename), 'r') as file:
            for line in file:
                new_match = new_token_pattern.match(line)
                if new_match:
                    timestamp = datetime.strptime(new_match.group(1), "%Y-%m-%d %H:%M:%S,%f")
                    tags = [f"{tag[0]}({tag[1]})" for tag in tag_pattern.findall(new_match.group(2))]
                    token_info[new_match.group(3)] = {'time': timestamp, 'tags': tags}

                fill_match = filled_token_pattern.match(line)
                if fill_match:
                    timestamp = datetime.strptime(fill_match.group(1), "%Y-%m-%d %H:%M:%S,%f")
                    filled_tokens[fill_match.group(2)] = timestamp

# Sorting tokens based on waiting time
sorted_tokens = sorted(token_info.keys(), key=lambda x: filled_tokens.get(x, datetime.now()) - token_info[x]['time'],
                       reverse=True)

print("==== FILLED TOKENS ====")
for token in sorted_tokens:
    if token in filled_tokens:
        waiting_time = filled_tokens[token] - token_info[token]['time']
        formatted_wait_time = str(waiting_time).split('.')[0]  # To format as HH:MM:SS
        tags = ', '.join(token_info[token]['tags'])
        print(
            f"Token '{token}' (Requested: {tags}) created at {token_info[token]['time'].strftime('%Y-%m-%d %H:%M:%S')} waited for {formatted_wait_time} before being filled.")

print("\n==== UNFILLED TOKENS ====")
for token, info in token_info.items():
    if token not in filled_tokens:
        tags = ', '.join(info['tags'])
        print(
            f"Token '{token}' (Requested: {tags}) created at {info['time'].strftime('%Y-%m-%d %H:%M:%S')} was abandoned and not filled.")
