import requests

SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/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"

def send_error_to_slack(error_message, explanation, fix):
    message = f"""
🚨 *New Error Identified*

*Error:* `{error_message}`  
*Explanation:* {explanation}  
*Suggested Fix:* {fix}
"""
    response = requests.post(SLACK_WEBHOOK_URL, json={"text": message})
    if response.status_code == 200:
        print("✅ Sent to Slack")
    else:
        print(f"❌ Slack error: {response.status_code} - {response.text}")
