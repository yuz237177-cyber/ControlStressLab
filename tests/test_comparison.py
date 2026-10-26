"""Cross-experiment units, differences, unchanged metrics and independent snapshots."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from controlstresslab import comparison
from controlstresslab.experiment import default_config, execute, load_result, read_trace, Cancelled, export_zip


class ComparisonChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.root = Path(self.tmp.name)
        self.a,self.b = self.root/"baseline",self.root/"noise"
        c = default_config();execute(self.a,c)
        c["conditions"]["noise_std"] = .02;execute(self.b,c)
        self.entries = [dict(folder=str(p),case_id="PID_aw",label=name) for p,name in ((self.a,"基线"),(self.b,"噪声"))]

    def tearDown(self): self.tmp.cleanup()

    def test_differences_show_actual_changed_noise_only_and_keep_original_metrics(self):
        c = comparison.build(self.entries)
        fields = {x["field"] for x in c["differences"][0]["changes"]}
        self.assertEqual(fields,{"conditions.noise_std"})
        self.assertFalse(c["warnings"])
        for view in c["views"]:
            original = next(r for r in load_result(view["folder"])["records"] if r["case_id"] == "PID_aw")
            self.assertEqual(view["record"]["metrics"],original["metrics"])

    def test_units_duplicates_missing_case_and_tampered_source_rejected(self):
        with self.assertRaises(ValueError): comparison.build([self.entries[0],self.entries[0]])
        entries = deepcopy(self.entries);entries[1]["case_id"] = "missing"
        with self.assertRaises(ValueError): comparison.build(entries)
        p = self.root/"second";execute(p,default_config("second_order"))
        entries = deepcopy(self.entries);entries[1]["folder"] = str(p)
        with self.assertRaises(ValueError): comparison.build(entries)
        trace = self.b/"runs/PID_aw.csv";trace.write_bytes(trace.read_bytes()+b"changed")
        with self.assertRaises(ValueError): comparison.build(self.entries)

    def test_window_mismatch_and_multiple_factor_change_are_explicit(self):
        p = self.root/"window";c = default_config()
        c["conditions"].update(evaluation_start_s=1,noise_std=.02)
        c["plant"]["tau_s"] = 2;execute(p,c)
        entries = deepcopy(self.entries);entries[1]["folder"] = str(p)
        result = comparison.build(entries)
        self.assertTrue(any("窗口" in w for w in result["warnings"]))
        self.assertTrue(any("多项" in w for w in result["warnings"]))

    def test_complete_snapshot_metrics_inputs_and_trace_bytes_preserved(self):
        output = self.root/"snapshot"
        comparison.execute(output,dict(schema="comparison-1.0",entries=self.entries))
        loaded = load_result(output)
        self.assertEqual(loaded["verification"],"校验通过")
        for entry,r in zip(self.entries,loaded["records"]):
            original = next(r for r in load_result(Path(entry["folder"]))["records"] if r["case_id"] == "PID_aw")
            self.assertEqual(r["metrics"],original["metrics"])
            self.assertEqual((output/r["trace_file"]).read_bytes(),(Path(entry["folder"])/original["trace_file"]).read_bytes())
            self.assertEqual((output/r["input_file"]).read_bytes(),(Path(entry["folder"])/original["input_file"]).read_bytes())
            self.assertEqual(read_trace(output,r),read_trace(Path(entry["folder"]),original))
        self.assertTrue(export_zip(output,self.root/"snapshot.zip").is_file())
        with self.assertRaises(FileExistsError): comparison.execute(output,dict(schema="comparison-1.0",entries=self.entries))

    def test_snapshot_still_loads_after_original_temp_sources_are_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/"snapshot"
            with tempfile.TemporaryDirectory() as source_tmp:
                paths = [Path(source_tmp)/str(i) for i in range(2)]
                for i,p in enumerate(paths):
                    c = default_config();c["plant"]["tau_s"] = 1+i;execute(p,c)
                entries = [dict(folder=str(p),case_id="PID_aw",label=str(i)) for i,p in enumerate(paths)]
                comparison.execute(output,dict(schema="comparison-1.0",entries=entries))
            self.assertFalse(paths[0].exists())
            saved = load_result(output)
            self.assertEqual(saved["verification"],"校验通过")
            self.assertEqual(len(read_trace(output,saved["records"][0])),1201)

    def test_partial_cancellation_and_source_change_during_copy(self):
        p = self.root/"cancel"
        with self.assertRaises(Cancelled):
            comparison.execute(p,dict(schema="comparison-1.0",entries=self.entries),should_cancel=lambda:len(list((p/"runs").glob("*.json")))>=1)
        loaded = load_result(p)
        self.assertEqual(loaded["status"]["state"],"interrupted")
        self.assertEqual(len(loaded["records"]),1)
        changed = []
        def mutate(event):
            if not changed:
                path = self.a/"runs/PID_aw.csv";path.write_bytes(path.read_bytes()+b"changed");changed.append(True)
        p = self.root/"race"
        with self.assertRaises(ValueError): comparison.execute(p,dict(schema="comparison-1.0",entries=self.entries),progress=mutate)
        self.assertEqual(load_result(p)["status"]["state"],"export_failure")


if __name__ == "__main__": unittest.main()
