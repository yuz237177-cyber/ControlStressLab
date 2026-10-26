"""Finite-grid contracts, paired randomness, frozen parameters and artifacts."""
from copy import deepcopy
import json
import hashlib
import importlib.util
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from controlstresslab.robustness import default_config, validate_config, run_count, case_configs, execute, summarize, classify
from controlstresslab.experiment import default_config as experiment_config, load_result, read_trace, scenario_for, Cancelled, MODELS, export_zip
from controlstresslab.benchmark_design import controller_for
from controlstresslab.simulation import simulate


def small(model="first_order"):
    c = default_config(experiment_config(model))
    c["axes"][0]["values"] = [.5,1.5]
    c["axes"][1]["values"] = [0,.05]
    c["seeds"] = [11,22]
    c["base"]["conditions"]["noise_std"] = .01
    return c


class ScanChecks(unittest.TestCase):
    def test_count_full_factorial_and_detached_controller_configs(self):
        c = small()
        self.assertEqual(run_count(validate_config(c)),16)
        cases = list(case_configs(c))
        self.assertEqual(len(cases),8)
        self.assertEqual(len({(x,y,s) for x,y,s,_ in cases}),8)
        for x,y,seed,value in cases:
            self.assertEqual(value["controllers"],c["base"]["controllers"])
            self.assertEqual(value["conditions"]["seed"],seed)
            self.assertEqual(value["plant"]["tau_s"],c["axes"][0]["values"][x])
        cases[0][3]["controllers"][0]["parameters"]["kp"] = 100
        self.assertNotEqual(cases[1][3]["controllers"][0]["parameters"]["kp"],100)

    def test_strict_axes_types_order_seeds_budget_and_thresholds(self):
        changes = [("extra",1),("schema","future"),("max_runs",True),("max_runs",2),
            ("axes",[]),("axes",[{"key":"plant.mass_kg","values":[1]}]),
            ("axes",[{"key":"plant.tau_s","values":[1,1]}]),
            ("axes",[{"key":"plant.tau_s","values":[2,1]}]),
            ("axes",[{"key":"plant.tau_s","values":[True]}]),
            ("axes",[{"key":"plant.tau_s","values":[float("nan")]}]),
            ("seeds",[True]),("seeds",[1,1]),("seeds",[])]
        for key,value in changes:
            c = small();c[key] = value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError): validate_config(c)
        c = small();c["axes"][1] = deepcopy(c["axes"][0])
        with self.assertRaises(ValueError): validate_config(c)
        for value in (-1, True, float("inf")):
            c = small();c["thresholds"]["rmse_max"] = value
            with self.assertRaises(ValueError): validate_config(c)
        c = small();c["thresholds"] = {k:None for k in c["thresholds"]}
        with self.assertRaises(ValueError): validate_config(c)

    def test_every_cell_validated_before_output_and_no_silent_time_rounding(self):
        c = small();c["axes"][1]["values"] = [0,.015]
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/"invalid"
            with self.assertRaises(ValueError): execute(p,c)
            self.assertFalse(p.exists())

    def test_sample_budget_and_constant_disturbance_guard(self):
        c = small();c["base"]["conditions"]["dt_s"] = .00001
        with self.assertRaises(ValueError): validate_config(c)
        c = small();c["base"]["disturbance"]["kind"] = "constant"
        c["axes"] = [dict(key="disturbance.amplitude",values=[0,.1])]
        with self.assertRaises(ValueError): validate_config(c)

    def test_two_models_and_all_controllers_match_original_core(self):
        with tempfile.TemporaryDirectory() as tmp:
            for model in ("first_order","second_order"):
                c = small(model);c["seeds"] = [11];c["axes"] = c["axes"][:1]
                c["base"]["selected_controllers"] = [d["name"] for d in c["base"]["controllers"]]
                p = Path(tmp)/model
                execute(p,c)
                loaded = load_result(p)
                self.assertEqual(loaded["verification"],"校验通过")
                self.assertEqual(len(loaded["records"]),8)
                for record in loaded["records"]:
                    value = record["run_config"]
                    params = next(d["parameters"] for d in value["controllers"] if d["name"] == record["controller_name"])
                    core = simulate(MODELS[model](**value["plant"]),controller_for(record["controller_name"],params),scenario_for(value))
                    rows = read_trace(p,record)
                    self.assertEqual([r["output"] for r in rows],[r["true_output_rad_s"] for r in core.rows])
                    self.assertEqual([r["applied_input"] for r in rows],[r["applied_V"] for r in core.rows])
                    self.assertEqual(record["run_config"]["controllers"],c["base"]["controllers"])
                    self.assertEqual(rows[-1]["applied_input"],None)

    def test_same_cell_noise_pairing_and_scaled_seed_basis_across_cells(self):
        c = small();c["axes"] = [dict(key="conditions.noise_std",values=[.01,.03])]
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/"scan";execute(p,c)
            records = load_result(p)["records"]
            for seed in c["seeds"]:
                for x,std in enumerate((.01,.03)):
                    group = [r for r in records if r["axis_indices"] == [x,0] and r["seed"] == seed]
                    self.assertEqual(len({r["input_sha256"] for r in group}),1)
                    saved = json.loads((p/group[0]["input_file"]).read_text(encoding="utf8"))["noise"]
                    rng = random.Random(seed)
                    expected = [rng.gauss(0,std) for _ in saved]
                    self.assertEqual(saved,expected)

    def test_thresholds_are_separate_from_failure_status_and_include_boundaries(self):
        thresholds = dict(rmse_max=.2,saturation_fraction_max=.1,input_variation_rate_max=None)
        m = dict(status="completed",rmse=.2,saturation_fraction=.1)
        self.assertEqual(classify(m,thresholds),"met")
        m["rmse"] = .20001
        self.assertEqual(classify(m,thresholds),"not_met")
        m.update(status="aborted",rmse=None)
        self.assertEqual(classify(m,thresholds),"run_failed")

    def test_failed_or_missing_seed_masks_numeric_cell_and_worst_excludes_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = small();p = Path(tmp)/"scan";execute(p,c)
            records = load_result(p)["records"]
            records[0]["metrics"].update(status="aborted",rmse=None)
            records[0]["requirement"] = "run_failed"
            result = summarize(records,c)
            cell = next(x for x in result["cells"] if x["controller_name"] == records[0]["controller_name"] and x["axis_indices"] == records[0]["axis_indices"])
            self.assertEqual(cell["requirement"],"run_failed")
            self.assertTrue(all(v is None for v in cell["worst_observed"].values()))
            self.assertNotEqual(result["worst_completed_rmse_case"][records[0]["controller_name"]],records[0]["case_id"])
            cell = summarize(records[:1],c)["cells"][0]
            self.assertEqual(cell["requirement"],"incomplete")

    def test_export_complete_with_failed_runs_nulls_and_zip_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = small();c["base"]["conditions"]["output_bound"] = .001
            p = Path(tmp)/"failed";_,failed = execute(p,c)
            loaded = load_result(p)
            self.assertEqual(failed,16)
            self.assertEqual(loaded["status"]["state"],"completed_with_failures")
            self.assertTrue(all(r["metrics"]["rmse"] is None for r in loaded["records"]))
            self.assertTrue(export_zip(p,Path(tmp)/"failed.zip").exists())
            with self.assertRaises(FileExistsError): execute(p,c)

    def test_cancellation_partial_and_plot_failure_never_mark_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = small();p = Path(tmp)/"cancel"
            with self.assertRaises(Cancelled):
                execute(p,c,should_cancel=lambda: len(list((p/"runs").glob("*.json")))>=1)
            loaded = load_result(p)
            self.assertEqual(loaded["status"]["state"],"interrupted")
            self.assertEqual(len(loaded["records"]),1)
            self.assertFalse(loaded["status"]["artifacts_complete"])
            p = Path(tmp)/"plot_fail"
            with patch("controlstresslab.robustness_plots.build",side_effect=OSError("disk")),self.assertRaises(OSError): execute(p,c,plots=True)
            self.assertEqual(load_result(p)["status"]["state"],"export_failure")
            self.assertEqual(len(load_result(p)["records"]),16)

    def test_independent_csv_audit_and_metric_tampering_negative_control(self):
        spec = importlib.util.spec_from_file_location("scan_evidence_audit",ROOT/"scripts/check_scan_evidence.py")
        module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/"scan";execute(p,small())
            self.assertTrue(module.audit(p)["passed"])
            record_path = next((p/"runs").glob("*.json"))
            record = json.loads(record_path.read_text(encoding="utf8"))
            record["metrics"]["rmse"] += .5
            record_path.write_text(json.dumps(record),encoding="utf8")
            checks = json.loads((p/"checksums.json").read_text(encoding="utf8"))
            checks[record_path.relative_to(p).as_posix()] = hashlib.sha256(record_path.read_bytes()).hexdigest()
            (p/"checksums.json").write_text(json.dumps(checks),encoding="utf8")
            with self.assertRaisesRegex(AssertionError,"rmse"):module.audit(p)


if __name__ == "__main__": unittest.main()
