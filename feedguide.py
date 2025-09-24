from parser import FeedGuideRunner
import asyncio
  # or define inline

philly_feed = {
  "feed_name": "PhillyFed_MFG",
  "steps": [
    {"action": "goto", "url": "https://www.philadelphiafed.org"},
    {"action": "click", "text": "Surveys & Data"},
    {"action": "click", "text": "Manufacturing Business Outlook Survey"},
    {"action": "click", "text": "Download the full history"},
    {"action": "download", "text": "bos_history.xls", "save_as": "bos_history.xls"}
  ]
}

runner = FeedGuideRunner(download_dir="./downloads", headless=False, reuse_browser=False)
res = runner.run(philly_feed)
print(res)
