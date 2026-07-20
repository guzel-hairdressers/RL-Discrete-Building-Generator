"""Static protocol and accessibility checks for the dependency-free client."""

from __future__ import annotations

from html.parser import HTMLParser
import pathlib
import shutil
import subprocess
import unittest


MODULE_DIR = pathlib.Path(__file__).resolve().parents[1]
HTML_PATH = MODULE_DIR / "index.html"
APP_PATH = MODULE_DIR / "app.js"
STYLE_PATH = MODULE_DIR / "styles.css"


class ElementCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elements: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append((tag, dict(attrs)))


class FrontendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = HTML_PATH.read_text(encoding="utf-8")
        cls.app = APP_PATH.read_text(encoding="utf-8")
        cls.styles = STYLE_PATH.read_text(encoding="utf-8")
        cls.parser = ElementCollector()
        cls.parser.feed(cls.html)

    def test_required_controls_exist_once(self) -> None:
        identifiers = [attrs.get("id") for _, attrs in self.parser.elements if attrs.get("id")]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        required = {
            "planCanvas",
            "pauseBtn",
            "newSiteBtn",
            "resetPolicyBtn",
            "saveCheckpointBtn",
            "parallelEnvironments",
            "coreSpacing",
            "publicMode",
            "singleFloor",
            "boundaryType",
            "atriumPolicy",
            "canvasAccessibleSummary",
            "siteMetricList",
        }
        self.assertTrue(required.issubset(set(identifiers)))

    def test_every_range_has_a_keyboard_editable_number_pair(self) -> None:
        elements_by_id = {
            attrs["id"]: (tag, attrs)
            for tag, attrs in self.parser.elements
            if attrs.get("id")
        }
        ranges = [
            attrs
            for tag, attrs in self.parser.elements
            if tag == "input" and attrs.get("type") == "range"
        ]
        self.assertGreater(len(ranges), 0)
        for range_attrs in ranges:
            range_id = range_attrs["id"]
            with self.subTest(range_id=range_id):
                pair = elements_by_id.get(f"{range_id}Num")
                self.assertIsNotNone(pair)
                self.assertEqual(pair[1].get("type"), "number")
                self.assertEqual(pair[1].get("min"), range_attrs.get("min"))
                self.assertEqual(pair[1].get("max"), range_attrs.get("max"))
                self.assertEqual(pair[1].get("step"), range_attrs.get("step"))

    def test_geometry_controls_match_canonical_hard_limits(self) -> None:
        elements_by_id = {
            attrs["id"]: attrs
            for _, attrs in self.parser.elements
            if attrs.get("id")
        }
        for identifier in ("minEdge", "maxEdge", "minEdgeNum", "maxEdgeNum"):
            self.assertEqual(elements_by_id[identifier].get("min"), "1")
            self.assertEqual(elements_by_id[identifier].get("max"), "9")
        for identifier in ("maxEdges", "maxEdgesNum"):
            self.assertEqual(elements_by_id[identifier].get("min"), "3")
            self.assertEqual(elements_by_id[identifier].get("max"), "8")

    def test_triangle_penalty_copy_matches_canonical_formula(self) -> None:
        self.assertIn("-8.0 pts/average triangle", self.app)
        self.assertNotIn("-1.5 to -8.0 pts/ea", self.app)
        self.assertIn("-8.0 pts/average triangle", self.html)
        self.assertIn("metrics.reusedBpeModules", self.app)
        self.assertIn("globally reused module occurrences", self.app)

    def test_client_is_self_contained_and_response_driven(self) -> None:
        external_assets = [
            attrs.get("src") or attrs.get("href")
            for tag, attrs in self.parser.elements
            if tag in {"script", "link"} and (attrs.get("src") or attrs.get("href"))
        ]
        self.assertTrue(all(not value.startswith(("http://", "https://", "//")) for value in external_assets))
        self.assertIn("stepInFlight", self.app)
        self.assertIn("generationId", self.app)
        self.assertIn("scheduleWallCache", self.app)
        self.assertIn("requestIdleCallback", self.app)
        self.assertNotIn("ws://localhost", self.app)

    def test_recoverable_transactions_keep_an_accepted_settings_snapshot(self) -> None:
        self.assertIn("acceptedSettings: null", self.app)
        self.assertIn("pendingSettings: null", self.app)
        self.assertIn("state.acceptedSettings = copySettings(state.pendingSettings)", self.app)
        self.assertIn("recoverRejectedSettings()", self.app)
        self.assertIn("restoreSettingsControls(state.acceptedSettings)", self.app)
        self.assertIn("resynchronizeAcceptedSettings('Step tokens changed", self.app)
        self.assertIn("scheduleNextStep(80)", self.app)

    def test_vector_wall_work_is_offloaded_and_cancellable(self) -> None:
        self.assertIn("new Blob([workerSource]", self.app)
        self.assertIn("new Worker(objectUrl)", self.app)
        self.assertIn("worker.postMessage({ token, placements: snapshot })", self.app)
        self.assertIn("window.cancelIdleCallback(state.wallSchedule.id)", self.app)
        self.assertIn("state.wallWorker.terminate()", self.app)
        self.assertIn("if (!isWallJobCurrent(token, revision, generationId, episode)) return;", self.app)
        self.assertIn("payload.token !== token", self.app)

        resume_index = self.app.index("cancelWallJob();", self.app.index("function toggleTraining"))
        next_episode_index = self.app.index("if (state.pendingNextEpisode", resume_index)
        self.assertLess(resume_index, next_episode_index)

        request_index = self.app.index("function prepareForSiteRequest")
        request_end = self.app.index("function resetPolicy", request_index)
        self.assertIn("cancelWallJob();", self.app[request_index:request_end])

    def test_responsive_panel_has_modal_focus_semantics(self) -> None:
        self.assertIn("dom.controlsPanel.inert = !open", self.app)
        self.assertIn("setAttribute('aria-hidden', String(!open))", self.app)
        self.assertIn("setAttribute('aria-modal', 'true')", self.app)
        self.assertIn("dom.controlsPanel.contains(activeElement)", self.app)
        self.assertIn("event.key !== 'Tab'", self.app)
        self.assertIn("last.focus()", self.app)
        self.assertIn("first.focus()", self.app)

    def test_canvas_has_live_text_alternative_for_site_metrics(self) -> None:
        elements_by_id = {
            attrs["id"]: (tag, attrs)
            for tag, attrs in self.parser.elements
            if attrs.get("id")
        }
        canvas = elements_by_id["planCanvas"][1]
        summary = elements_by_id["canvasAccessibleSummary"][1]
        self.assertEqual(canvas.get("aria-describedby"), "canvasAccessibleSummary")
        self.assertEqual(summary.get("aria-live"), "polite")
        self.assertIn("function updateAccessibleSiteMetrics()", self.app)
        self.assertIn("Net site area", self.app)
        self.assertIn("scheduleAccessibleSiteMetrics()", self.app)

    def test_mobile_device_status_remains_visible(self) -> None:
        self.assertNotIn(".device-badge { display: none; }", self.styles)
        self.assertIn(".device-badge {\n    max-width: 112px;", self.styles)

    def test_placement_paths_are_cached_and_viewport_culled(self) -> None:
        self.assertIn("worldPath: createWorldPolygonPath(poly)", self.app)
        self.assertIn("boundsIntersect(placement.bounds, viewport)", self.app)
        self.assertIn("pointInsideBounds(placement.center, viewport)", self.app)
        self.assertIn("if (!boundsIntersect(edgeBounds, viewport)) continue;", self.app)
        draw_start = self.app.index("function drawPlacements")
        graph_start = self.app.index("function drawGraph", draw_start)
        self.assertNotIn("new Path2D", self.app[draw_start:graph_start])

    def test_websocket_defaults_to_same_origin(self) -> None:
        self.assertIn("const endpoint = new URL('/ws', origin)", self.app)
        self.assertIn("endpoint.protocol = scheme", self.app)
        self.assertNotIn("window.location.port === '8000'", self.app)

    def test_site_request_send_races_rollback_loading_state(self) -> None:
        self.assertIn("if (!sendCommand({ cmd: 'newSite' }))", self.app)
        self.assertIn("if (!sendCommand({ cmd: 'resetPolicy' }))", self.app)
        self.assertIn("function recoverFailedSiteRequest(reason)", self.app)
        self.assertIn("state.awaitingSite = false", self.app)

    def test_next_dictionary_is_deferred_until_episode_transition(self) -> None:
        done_start = self.app.index("function handleEpisodeDoneEvent")
        done_end = self.app.index("function handleAckEvent", done_start)
        done_handler = self.app[done_start:done_end]
        self.assertIn("state.pendingNextDictionary = Array.isArray(data.nextDictionary)", done_handler)
        self.assertIn("state.dictionary = data.dictionary", done_handler)

        next_start = self.app.index("function beginNextEpisode")
        next_end = self.app.index("function scheduleNextStep", next_start)
        next_handler = self.app[next_start:next_end]
        install_index = next_handler.index("state.dictionary = nextDictionary")
        send_index = next_handler.index("scheduleNextStep(80)")
        self.assertLess(install_index, send_index)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_javascript_syntax(self) -> None:
        result = subprocess.run(
            [shutil.which("node"), "--check", str(APP_PATH)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
