import json
import os
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

from scout import engine, extract
from scout.server import make_handler
from scout.store import Store, new_project, validate


def project(scene="pass", pay="pass", ai=4, moat=4, team=4, ev="有证据"):
    return new_project(
        name="t",
        l1={"scene": {"v": scene, "e": ev}, "pay": {"v": pay, "e": ev}},
        l2={"ai": {"v": ai, "e": ev}, "moat": {"v": moat, "e": ev}, "team": {"v": team, "e": ev}},
    )


class EngineTest(unittest.TestCase):
    def test_l1_fail_is_veto_even_with_high_scores(self):
        ev = engine.evaluate(project(pay="fail", ai=5, moat=5, team=5))
        self.assertEqual(ev["stage"], "初筛未通过")
        self.assertEqual(ev["reasons"], ["需求弱 / 无付费意愿"])

    def test_l1_unknown_asks_for_more_interview(self):
        self.assertEqual(engine.evaluate(project(scene="unk"))["stage"], "待补访谈")

    def test_unscored_l2_is_in_progress(self):
        self.assertEqual(engine.evaluate(project(moat=0))["stage"], "复筛中")

    def test_recommend_needs_line_and_no_weak_dimension(self):
        self.assertEqual(engine.evaluate(project())["stage"], "建议推荐")
        # 总分过线但有一项 2 分：不推荐，原因指向短板
        ev = engine.evaluate(project(ai=5, moat=2, team=5))
        self.assertGreaterEqual(ev["total"], 3.8)
        self.assertEqual(ev["stage"], "初筛未通过")
        self.assertEqual(ev["reasons"], ["缺数据 / 工作流壁垒"])

    def test_below_line_blames_weakest(self):
        ev = engine.evaluate(project(ai=3, moat=4, team=3))
        self.assertEqual(ev["stage"], "初筛未通过")
        self.assertIn(ev["reasons"][0], ["AI 非必要", "团队验证不足"])

    def test_human_decision_overrides_suggestion(self):
        p = project(pay="fail")
        p["decision"] = "rec"
        self.assertEqual(engine.final_stage(p)["stage"], "已推荐")

    def test_missing_evidence(self):
        p = project(ev="")
        self.assertEqual(len(engine.missing_evidence(p)), 5)

    def test_summary_counts_reasons(self):
        s = engine.summary([project(), project(pay="fail"), project(scene="fail", pay="fail")])
        self.assertEqual(s["funnel"][0], ["访谈", 3])
        self.assertEqual(s["funnel"][1], ["过第一层", 1])
        self.assertEqual(dict(s["reasons"])["需求弱 / 无付费意愿"], 2)


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "t.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_roundtrip_and_order(self):
        a, b = self.store.save(project()), self.store.save(project())
        self.assertEqual([p["id"] for p in self.store.list()], [b["id"], a["id"]])
        self.assertTrue(self.store.delete(a["id"]))
        self.assertIsNone(self.store.get(a["id"]))

    def test_seed(self):
        self.store.seed_if_empty()
        self.assertEqual(len(self.store.list()), 6)

    def test_validate_rejects_bad_values(self):
        with self.assertRaises(ValueError):
            validate({"l2": {"ai": {"v": 9}}})
        with self.assertRaises(ValueError):
            validate({"l1": {"scene": {"v": "maybe"}}})


class ExtractTest(unittest.TestCase):
    TX = "我们上门跑了 12 家店。现在有 2 家店已经按 99 元一个月付了第一个月。"

    def test_verify_drops_fabricated_quotes(self):
        out = extract.verify([
            {"key": "pay", "v": "pass", "quote": "2 家店已经按 99 元一个月付了第一个月"},
            {"key": "scene", "v": "pass", "quote": "我们服务了 500 家连锁店"},
            {"key": "ai", "v": 9, "quote": "上门跑了12家店"},
            {"key": "nope", "v": "pass", "quote": "x"},
        ], self.TX)
        self.assertEqual(out["pay"]["v"], "pass")
        self.assertEqual(out["scene"]["v"], "unk")
        self.assertEqual(out["scene"]["quote"], "")
        self.assertEqual(out["ai"]["v"], 5)  # 越界分数收敛到 5；引用忽略空白差异
        self.assertNotIn("nope", out)

    def test_keyword_fallback_without_key(self):
        with mock.patch.dict(os.environ, {"ARK_API_KEY": "", "ARK_BASE_URL": ""}):
            r = extract.suggest(self.TX)
        self.assertEqual(r["mode"], "keyword")
        self.assertIn("99 元", r["items"]["pay"]["quote"])
        self.assertEqual(r["items"]["pay"]["v"], "unk")


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        store = Store(os.path.join(self.tmp.name, "t.db"))
        store.seed_if_empty()
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def req(self, method, path, body=None):
        r = urllib.request.Request(self.base + path, method=method,
                                   data=json.dumps(body).encode() if body is not None else None,
                                   headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(r) as res:
                return res.status, json.load(res)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def test_crud_and_report(self):
        code, items = self.req("GET", "/api/projects")
        self.assertEqual((code, len(items)), (200, 6))
        self.assertIn("eval", items[0])
        code, p = self.req("POST", "/api/projects", {"name": "新项目"})
        self.assertEqual(code, 201)
        p["l1"]["pay"]["v"] = "fail"
        code, p2 = self.req("PUT", f"/api/projects/{p['id']}", p)
        self.assertEqual(p2["eval"]["stage"], "初筛未通过")
        code, rep = self.req("GET", "/api/report")
        self.assertEqual(rep["funnel"][0][1], 7)
        self.assertIn("新项目", rep["checklist"])

    def test_bad_input_is_400(self):
        code, _ = self.req("PUT", "/api/projects/ex-dorm", {"l2": {"ai": {"v": 7}}})
        self.assertEqual(code, 400)

    def test_static_index(self):
        with urllib.request.urlopen(self.base + "/") as r:
            self.assertIn("Scout 项目筛选台", r.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
