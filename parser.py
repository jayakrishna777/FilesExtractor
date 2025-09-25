# feedguide_runner.py
import os
import time
import requests
from typing import Dict, List, Any, Optional
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


class FeedGuideRunner:
    """
    Generic runner to execute a feed guide (list of step dicts) and download files.
    Supports actions: goto, click, download, wait, wait_for_selector, fill, click_new_page.
    """

    def __init__(
        self,
        download_dir: str = "./downloads",
        headless: bool = True,
        browser_name: str = "chromium",
        step_timeout_ms: int = 30000,
        reuse_browser: bool = False,
    ):
        self.download_dir = os.path.abspath(download_dir)
        os.makedirs(self.download_dir, exist_ok=True)
        self.headless = headless
        self.browser_name = browser_name
        self.step_timeout = step_timeout_ms
        self.reuse_browser = reuse_browser
        self._playwright = None
        self._browser = None
        self._context = None

        if self.reuse_browser:
            self._start_browser()

    def _start_browser(self):
        if self._browser:
            return
        self._playwright = sync_playwright().start()
        browser_launcher = getattr(self._playwright, self.browser_name)
        self._browser = browser_launcher.launch(headless=self.headless)
        self._context = self._browser.new_context(accept_downloads=True)

    def _stop_browser(self):
        if self._context:
            self._context.close()
            self._context = None
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None

    def _ensure_page(self):
        if not self.reuse_browser:
            # ephemeral browser per run
            self._start_browser()
            page = self._context.new_page()
            return page, True  # page, created_now
        else:
            if not self._context:
                self._start_browser()
            page = self._context.new_page()
            return page, True

    def _safe_click_by_text(self, page, text: str):
        # try Playwright text selector (first), fallback to searching anchors/buttons
        try:
            locator = page.get_by_text(text, exact=False)
            locator.first.click(timeout=self.step_timeout)
            return True, f"Clicked by text='{text}'"
        except Exception:
            # fallback: iterate anchors
            try:
                anchors = page.query_selector_all("a, button, [role='link'], [role='button']")
                for a in anchors:
                    try:
                        inner = (a.inner_text() or "").strip()
                        if not inner:
                            continue
                        if text.lower() in inner.lower():
                            a.click(timeout=self.step_timeout)
                            return True, f"Clicked fallback element with text='{inner}'"
                    except Exception:
                        continue
            except Exception:
                pass
        return False, f"Element with text '{text}' not found"

    def _download_via_requests(self, url: str, save_as: Optional[str] = None) -> Dict[str, Any]:
        try:
            resp = requests.get(url, stream=True, timeout=60)
            resp.raise_for_status()
            filename = save_as or url.split("/")[-1] or "download.bin"
            dest = os.path.join(self.download_dir, filename)
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
            return {"ok": True, "file": dest}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def run(self, feed_guide: Dict[str, Any]) -> Dict[str, Any]:
        """
        feed_guide: {
           "feed_name": "...",
           "steps": [
                {"action":"goto", "url": "..."},
                {"action":"click", "selector":"...", "continue_on_error":False},
                {"action":"click", "text":"Surveys and Data"},
                {"action":"download", "selector":"text=bos_history.xls", "save_as":"bos_history.xls"},
                {"action":"download", "url":"https://example.com/file.xls", "save_as": "..."}
           ]
        }
        """
        results = {"feed_name": feed_guide.get("feed_name"), "steps": [], "downloads": []}
        steps: List[Dict[str, Any]] = feed_guide.get("steps", [])
        page, created =  self._ensure_page()

        try:
            for idx, step in enumerate(steps, start=1):
                action = (step.get("action") or "").lower()
                step_result = {"step": idx, "action": action, "raw": step}
                try:
                    if action == "goto":
                        url = step["url"]
                        page.goto(url, timeout=self.step_timeout)
                        step_result["status"] = "ok"
                        step_result["info"] = f"Navigated to {url}"

                    elif action == "wait":
                        secs = float(step.get("seconds", 1))
                        time.sleep(secs)
                        step_result["status"] = "ok"
                        step_result["info"] = f"Waited {secs}s"

                    elif action == "wait_for_selector":
                        selector = step["selector"]
                        page.wait_for_selector(selector, timeout=self.step_timeout)
                        step_result["status"] = "ok"
                        step_result["info"] = f"Selector ready: {selector}"

                    elif action == "fill":
                        selector = step["selector"]
                        value = step.get("value", "")
                        page.fill(selector, value, timeout=self.step_timeout)
                        step_result["status"] = "ok"
                        step_result["info"] = f"Filled {selector}"

                    elif action in ("click", "click_text"):
                        selector = step.get("selector")
                        text = step.get("text")
                        # click that may cause navigation (follow)
                        if selector:
                            page.click(selector, timeout=self.step_timeout)
                            step_result["status"] = "ok"
                            step_result["info"] = f"Clicked selector: {selector}"
                        elif text:
                            ok, info = self._safe_click_by_text(page, text)
                            step_result["status"] = "ok" if ok else "error"
                            step_result["info"] = info
                            if not ok and not step.get("continue_on_error", False):
                                raise RuntimeError(info)
                        else:
                            raise ValueError("click requires selector or text")

                    elif action == "click_new_page":
                        # click triggers a new page (tab); we wait for that page and optionally follow it
                        selector = step.get("selector")
                        text = step.get("text")
                        if selector:
                            with self._context.expect_page() as new_page_info:
                                page.click(selector, timeout=self.step_timeout)
                            new_page = new_page_info.value
                            new_page.wait_for_load_state("load", timeout=self.step_timeout)
                            page = new_page  # follow new page for subsequent actions
                            step_result["status"] = "ok"
                            step_result["info"] = "Opened new page via selector"
                        elif text:
                            with self._context.expect_page() as new_page_info:
                                ok, info = self._safe_click_by_text(page, text)
                            new_page = new_page_info.value
                            new_page.wait_for_load_state("load", timeout=self.step_timeout)
                            page = new_page
                            step_result["status"] = "ok"
                            step_result["info"] = "Opened new page via text"
                        else:
                            raise ValueError("click_new_page needs selector or text")

                    elif action == "download":
                        # preferred: if url provided => direct requests download
                        if "url" in step:
                            r = self._download_via_requests(step["url"], save_as=step.get("save_as"))
                            step_result.update(r)
                            if r.get("ok"):
                                results["downloads"].append(r["file"])

                        else:
                            selector = step.get("selector")
                            text = step.get("text")
                            # we will use Playwright's expect_download
                            if selector or text:
                                try:
                                    if selector:
                                        with page.expect_download() as download_info:
                                            page.click(selector, timeout=self.step_timeout)
                                        download = download_info.value
                                    elif text:
                                        with page.expect_download() as download_info:
                                            ok, info = self._safe_click_by_text(page, text)
                                            if not ok:
                                                raise RuntimeError(info)
                                        download = download_info.value
                                    else:
                                        raise ValueError("No selector or text provided")
                                    # save the file locally
                                    download.save_as("bos_history.xls")
                                    print("✅ File downloaded:",  download.path())

                                   
                                    suggested = download.suggested_filename or step.get("save_as") or "download.bin"
                                    save_as = step.get("save_as", suggested)
                                    dest = os.path.join(self.download_dir, save_as)
                                    download.save_as(dest)
                                    step_result["status"] = "ok"
                                    step_result["file"] = dest
                                    results["downloads"].append(dest)
                                except PlaywrightTimeoutError as e:
                                    step_result["status"] = "error"
                                    step_result["error"] = f"download timeout: {str(e)}"
                                    if not step.get("continue_on_error", False):
                                        raise
                            else:
                                raise ValueError("download needs selector/text/url")

                    else:
                        step_result["status"] = "error"
                        step_result["error"] = f"Unknown action: {action}"
                        if not step.get("continue_on_error", False):
                            raise RuntimeError(step_result["error"])

                except Exception as e:
                    step_result["status"] = "error"
                    step_result["error"] = str(e)
                    # stop or continue based on flag
                    if step.get("continue_on_error", False):
                        results["steps"].append(step_result)
                        continue
                    else:
                        results["steps"].append(step_result)
                        raise

                results["steps"].append(step_result)

        finally:
            # cleanup page if ephemeral
            try:
                page.close()
            except Exception:
                pass
            if not self.reuse_browser:
                self._stop_browser()

        return results
