#!/usr/bin/env python3
"""
UI Capture - Visual Debugging via Playwright
=============================================

Provides UI debugging capabilities:
- Screenshot capture
- DOM snapshot
- Console error collection
- Network request logging
- WebSocket message capture

Integrates with Playwright for browser automation.
"""

import json
import asyncio
import base64
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger("debug-mcp.ui_capture")

# Try to import playwright
try:
    from playwright.async_api import async_playwright, Browser, Page, ConsoleMessage
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not installed. Install with: pip install playwright && playwright install")


class UICapture:
    """
    Captures UI state for visual debugging using Playwright.

    Features:
    - Screenshot capture (full page or specific element)
    - DOM snapshot
    - Console error collection
    - Network request/response logging
    - WebSocket message capture
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        screenshots_dir: Optional[Path] = None
    ):
        self.base_url = base_url
        self.screenshots_dir = screenshots_dir or Path(__file__).parent.parent.parent / ".hive-mind" / "screenshots"
        self._browser: Optional["Browser"] = None
        self._playwright = None
        self._console_messages: List[Dict[str, Any]] = []
        self._network_requests: List[Dict[str, Any]] = []

    async def _ensure_browser(self) -> "Browser":
        """Ensure browser is launched."""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright not installed")

        if self._browser is None or not self._browser.is_connected():
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--no-sandbox"
                ]
            )

        return self._browser

    async def close(self):
        """Close browser and cleanup."""
        if self._browser:
            await self._browser.close()
            self._browser = None

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def capture_state(
        self,
        url: Optional[str] = None,
        selector: Optional[str] = None,
        wait_for_network_idle: bool = True
    ) -> Dict[str, Any]:
        """
        Capture current UI state including screenshot and DOM.

        Args:
            url: URL to capture (defaults to base_url)
            selector: CSS selector to capture specific element
            wait_for_network_idle: Wait for network to be idle before capture

        Returns:
            UI state with screenshot path, DOM snapshot, and metadata
        """
        if not PLAYWRIGHT_AVAILABLE:
            return {
                "error": "Playwright not installed",
                "install_command": "pip install playwright && playwright install chromium"
            }

        target_url = url or self.base_url

        try:
            browser = await self._ensure_browser()
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="CAIO-Debug-Agent/1.0"
            )

            page = await context.new_page()

            # Collect console messages
            console_messages = []

            def on_console(msg: "ConsoleMessage"):
                console_messages.append({
                    "type": msg.type,
                    "text": msg.text,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

            page.on("console", on_console)

            # Navigate
            await page.goto(target_url, wait_until="networkidle" if wait_for_network_idle else "load")

            # Wait a bit for any dynamic content
            await page.wait_for_timeout(1000)

            # Capture screenshot
            self.screenshots_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = self.screenshots_dir / f"capture_{timestamp}.png"

            if selector:
                element = await page.query_selector(selector)
                if element:
                    await element.screenshot(path=str(screenshot_path))
                else:
                    await page.screenshot(path=str(screenshot_path), full_page=True)
            else:
                await page.screenshot(path=str(screenshot_path), full_page=True)

            # Get DOM snapshot
            dom_snapshot = await page.evaluate("""() => {
                function getNodeInfo(node, depth = 0) {
                    if (depth > 5) return null;
                    if (node.nodeType !== Node.ELEMENT_NODE) return null;

                    const info = {
                        tag: node.tagName.toLowerCase(),
                        id: node.id || undefined,
                        classes: node.className ? node.className.split(' ').filter(c => c) : undefined,
                        text: node.textContent?.slice(0, 100) || undefined
                    };

                    // Get relevant attributes
                    const attrs = ['href', 'src', 'data-testid', 'role', 'aria-label'];
                    attrs.forEach(attr => {
                        if (node.hasAttribute(attr)) {
                            info[attr] = node.getAttribute(attr);
                        }
                    });

                    // Get children (limited)
                    const children = [];
                    for (let i = 0; i < Math.min(node.children.length, 10); i++) {
                        const childInfo = getNodeInfo(node.children[i], depth + 1);
                        if (childInfo) children.push(childInfo);
                    }
                    if (children.length > 0) info.children = children;

                    return info;
                }

                return getNodeInfo(document.body);
            }""")

            # Get page metrics
            metrics = await page.evaluate("""() => {
                return {
                    title: document.title,
                    url: window.location.href,
                    scrollHeight: document.body.scrollHeight,
                    scrollWidth: document.body.scrollWidth,
                    viewportWidth: window.innerWidth,
                    viewportHeight: window.innerHeight,
                    documentReady: document.readyState,
                    errorCount: window.__errorCount || 0
                };
            }""")

            await context.close()

            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "url": target_url,
                "screenshot_path": str(screenshot_path),
                "screenshot_exists": screenshot_path.exists(),
                "dom_snapshot": dom_snapshot,
                "page_metrics": metrics,
                "console_messages": console_messages,
                "error_count": len([m for m in console_messages if m["type"] == "error"])
            }

        except Exception as e:
            logger.error(f"Failed to capture UI state: {e}")
            return {
                "error": str(e),
                "url": target_url,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    async def get_console_errors(
        self,
        url: Optional[str] = None,
        wait_seconds: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get browser console errors from the dashboard.

        Args:
            url: URL to check (defaults to base_url)
            wait_seconds: How long to wait and collect errors

        Returns:
            List of console errors with timestamps
        """
        if not PLAYWRIGHT_AVAILABLE:
            return [{
                "error": "Playwright not installed",
                "install_command": "pip install playwright && playwright install chromium"
            }]

        target_url = url or self.base_url
        console_errors = []

        try:
            browser = await self._ensure_browser()
            context = await browser.new_context()
            page = await context.new_page()

            def on_console(msg: "ConsoleMessage"):
                if msg.type in ["error", "warning"]:
                    console_errors.append({
                        "type": msg.type,
                        "text": msg.text,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "location": str(msg.location) if hasattr(msg, 'location') else None
                    })

            def on_page_error(error):
                console_errors.append({
                    "type": "exception",
                    "text": str(error),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

            page.on("console", on_console)
            page.on("pageerror", on_page_error)

            await page.goto(target_url, wait_until="networkidle")

            # Wait and collect errors
            await page.wait_for_timeout(wait_seconds * 1000)

            # Try to trigger potential error states
            await page.evaluate("""() => {
                // Trigger any lazy-loaded content
                window.scrollTo(0, document.body.scrollHeight);
                window.scrollTo(0, 0);
            }""")

            await page.wait_for_timeout(1000)

            await context.close()

        except Exception as e:
            logger.error(f"Failed to collect console errors: {e}")
            console_errors.append({
                "type": "capture_error",
                "text": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

        return console_errors

    async def capture_network_activity(
        self,
        url: Optional[str] = None,
        wait_seconds: int = 10
    ) -> Dict[str, Any]:
        """
        Capture network activity including requests and responses.

        Args:
            url: URL to monitor (defaults to base_url)
            wait_seconds: How long to monitor

        Returns:
            Network activity log
        """
        if not PLAYWRIGHT_AVAILABLE:
            return {
                "error": "Playwright not installed",
                "install_command": "pip install playwright && playwright install chromium"
            }

        target_url = url or self.base_url
        requests = []
        responses = []
        websocket_messages = []

        try:
            browser = await self._ensure_browser()
            context = await browser.new_context()
            page = await context.new_page()

            def on_request(request):
                requests.append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "url": request.url,
                    "method": request.method,
                    "resource_type": request.resource_type,
                    "headers": dict(request.headers) if request.headers else {}
                })

            def on_response(response):
                responses.append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "url": response.url,
                    "status": response.status,
                    "status_text": response.status_text,
                    "ok": response.ok
                })

            def on_websocket(ws):
                def on_frame_sent(payload):
                    websocket_messages.append({
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "direction": "sent",
                        "url": ws.url,
                        "payload": str(payload)[:500]
                    })

                def on_frame_received(payload):
                    websocket_messages.append({
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "direction": "received",
                        "url": ws.url,
                        "payload": str(payload)[:500]
                    })

                ws.on("framesent", on_frame_sent)
                ws.on("framereceived", on_frame_received)

            page.on("request", on_request)
            page.on("response", on_response)
            page.on("websocket", on_websocket)

            await page.goto(target_url, wait_until="networkidle")
            await page.wait_for_timeout(wait_seconds * 1000)

            await context.close()

            # Identify failed requests
            failed_requests = [r for r in responses if not r["ok"]]

            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "url": target_url,
                "duration_seconds": wait_seconds,
                "total_requests": len(requests),
                "total_responses": len(responses),
                "failed_count": len(failed_requests),
                "websocket_messages": len(websocket_messages),
                "requests": requests[-50:],  # Last 50
                "failed_requests": failed_requests,
                "websocket_activity": websocket_messages[-20:]  # Last 20
            }

        except Exception as e:
            logger.error(f"Failed to capture network activity: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    async def check_element_exists(
        self,
        selector: str,
        url: Optional[str] = None,
        timeout_ms: int = 5000
    ) -> Dict[str, Any]:
        """
        Check if a specific element exists on the page.

        Args:
            selector: CSS selector
            url: URL to check (defaults to base_url)
            timeout_ms: How long to wait for element

        Returns:
            Element existence and properties
        """
        if not PLAYWRIGHT_AVAILABLE:
            return {
                "error": "Playwright not installed"
            }

        target_url = url or self.base_url

        try:
            browser = await self._ensure_browser()
            context = await browser.new_context()
            page = await context.new_page()

            await page.goto(target_url, wait_until="networkidle")

            try:
                element = await page.wait_for_selector(selector, timeout=timeout_ms)

                if element:
                    # Get element properties
                    props = await element.evaluate("""(el) => {
                        const rect = el.getBoundingClientRect();
                        return {
                            visible: rect.width > 0 && rect.height > 0,
                            width: rect.width,
                            height: rect.height,
                            x: rect.x,
                            y: rect.y,
                            text: el.textContent?.slice(0, 200),
                            tag: el.tagName.toLowerCase(),
                            id: el.id,
                            classes: el.className
                        };
                    }""")

                    await context.close()

                    return {
                        "exists": True,
                        "selector": selector,
                        "url": target_url,
                        "properties": props
                    }

            except Exception:
                pass

            await context.close()

            return {
                "exists": False,
                "selector": selector,
                "url": target_url
            }

        except Exception as e:
            logger.error(f"Failed to check element: {e}")
            return {
                "error": str(e),
                "selector": selector,
                "url": target_url
            }

    async def get_page_errors(
        self,
        url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get JavaScript errors and React/Vue errors from the page.

        Args:
            url: URL to check

        Returns:
            Page error information
        """
        if not PLAYWRIGHT_AVAILABLE:
            return {"error": "Playwright not installed"}

        target_url = url or self.base_url

        try:
            browser = await self._ensure_browser()
            context = await browser.new_context()
            page = await context.new_page()

            js_errors = []
            page_errors = []

            def on_console(msg):
                if msg.type == "error":
                    js_errors.append({
                        "message": msg.text,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })

            def on_page_error(error):
                page_errors.append({
                    "message": str(error),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

            page.on("console", on_console)
            page.on("pageerror", on_page_error)

            await page.goto(target_url, wait_until="networkidle")
            await page.wait_for_timeout(3000)

            # Check for React error boundaries
            react_errors = await page.evaluate("""() => {
                const errors = [];
                // Look for React error boundary messages
                document.querySelectorAll('[data-reactroot]').forEach(el => {
                    if (el.textContent?.includes('Something went wrong')) {
                        errors.push(el.textContent.slice(0, 500));
                    }
                });
                // Look for error overlays
                const overlay = document.querySelector('#webpack-dev-server-client-overlay');
                if (overlay) {
                    errors.push('Webpack dev server error overlay detected');
                }
                return errors;
            }""")

            await context.close()

            return {
                "url": target_url,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "js_errors": js_errors,
                "page_errors": page_errors,
                "react_errors": react_errors,
                "total_errors": len(js_errors) + len(page_errors) + len(react_errors)
            }

        except Exception as e:
            logger.error(f"Failed to get page errors: {e}")
            return {
                "error": str(e),
                "url": target_url
            }
