# crew_tool_wrapper.py
from crewai.tools import BaseTool    # adjust import to your crewai package
from typing import Dict, Any
from parser import FeedGuideRunner

class FeedGuideNavigator(BaseTool):
    name: str = "feed_guide_navigator"
    description: str = "Executes a feed guide to navigate a site and download files"
    download_dir: str = "./downloads"

    def _run(self, feed_guide: Dict[str, Any]) -> Dict[str, Any]:
        runner = FeedGuideRunner(download_dir=self.download_dir, headless=True, reuse_browser=False)
        return runner.run(feed_guide)
