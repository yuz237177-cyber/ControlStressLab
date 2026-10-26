"""Portable project migration preserves immutable provenance and observation history."""
from copy import deepcopy
import hashlib,importlib.util,json,sys,tempfile,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"src"))
from controlstresslab import projects
from controlstresslab.experiment import default_config,load_result
AVAILABLE=importlib.util.find_spec("scipy") is not None
@unittest.skipUnless(AVAILABLE,"analysis optional dependencies")
class ProjectChecks(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def pipeline(self):
        from controlstresslab import tuning,tuning_protocol,tuning_validation
        project=projects.create(self.root/"original","中文研究",default_config(),"控制要求与动作之间的取舍")
        c=tuning_protocol.default_config();c["candidate_budget"]=2;c["thresholds"]["saturation_max"]=1.
        c["search"]["axes"]=c["search"]["axes"][:1];c["search"]["families"]=c["search"]["families"][:1];c["search"]["seeds"]=[11]
        c["validation"]["points"]=[{"plant.tau_s":.9}];c["validation"]["families"]=c["validation"]["families"][:1]
        c["validation"]["seeds"]=[22];c["validation"]["waveform_seeds"]=[33]
        projects.update_draft(project,c)
        tuning.execute(project/"results/search",c);projects.register(project,project/"results/search")
        tuning_validation.freeze(project/"results/selection",dict(search_folder=str(project/"results/search"),candidate_ids=[0],main_candidate_id=0,rationale="按声明要求保留基线，另设新工况核对"))
        projects.register(project,project/"results/selection")
        return project
    def test_migration_rebinds_by_content_without_rewriting_receipts(self):
        from controlstresslab.tuning_validation import execute
        original=self.pipeline();receipt=(original/"results/selection/selection.json").read_bytes()
        bundle=projects.export_bundle(original,self.root/"project.cslproj")
        original.rename(self.root/"unavailable-original")
        moved=projects.import_bundle(bundle,self.root/"中文新目录")
        self.assertEqual((moved/"results/selection/selection.json").read_bytes(),receipt)
        execute(moved/"results/validation",dict(selection_folder=str(moved/"results/selection")))
        projects.register(moved,moved/"results/validation")
        self.assertEqual(load_result(moved/"results/validation")["verification"],"校验通过")
        self.assertEqual(len(projects.read(moved)["entries"]),3)
    def test_clone_keeps_observation_history_and_new_identity(self):
        from controlstresslab import tuning_validation,tuning_protocol
        source=self.pipeline();tuning_validation.execute(source/"results/validation",dict(selection_folder=str(source/"results/selection")));projects.register(source,source/"results/validation")
        target=projects.clone(self.root/"branch",source,"新分支")
        p=projects.read(target);self.assertNotEqual(p["id"],projects.read(source)["id"])
        self.assertTrue(p["draft"]["observed_inputs"])
        with self.assertRaisesRegex(ValueError,"已观察"):tuning_protocol.prepare(p["draft"])
    def test_corrupt_result_and_overwrite_are_rejected(self):
        source=self.pipeline();(source/"results/search/summary.json").write_text("{}",encoding="utf-8")
        with self.assertRaises(ValueError):projects.export_bundle(source,self.root/"bad.cslproj")
        with self.assertRaises(FileExistsError):projects.create(source,"重复",default_config())
    def test_windows_transient_rename_retry_retains_atomic_json(self):
        from unittest.mock import patch
        from controlstresslab.experiment import atomic_json
        original=Path.replace;calls=[]
        def transient(path,target):
            calls.append(str(path))
            if len(calls)<3:
                error=PermissionError("temporary file sharing conflict");error.winerror=32;raise error
            return original(path,target)
        destination=self.root/"atomic.json"
        with patch.object(Path,"replace",transient),patch("time.sleep"):atomic_json(destination,dict(message="中文"))
        self.assertEqual(json.loads(destination.read_text(encoding="utf-8")),dict(message="中文"))
        self.assertEqual(len(calls),3)

    def test_archive_traversal_duplicate_and_tamper_are_rejected_before_import(self):
        for i,name in enumerate(("../escape","C:/escape","results\\escape","results/CON.txt")):
            archive=self.root/(str(i)+".zip")
            with zipfile.ZipFile(archive,"w") as z:z.writestr(name,"bad")
            dest=self.root/("import"+str(i))
            with self.assertRaises((ValueError,KeyError)):projects.import_bundle(archive,dest)
            self.assertFalse(dest.exists())
        source=self.pipeline();archive=projects.export_bundle(source,self.root/"good.cslproj")
        bad=self.root/"modified.zip"
        with zipfile.ZipFile(archive) as z,zipfile.ZipFile(bad,"w") as out:
            for name in z.namelist():out.writestr(name,b"{}" if name=="project.json" else z.read(name))
        with self.assertRaisesRegex(ValueError,"校验"):projects.import_bundle(bad,self.root/"tampered")
        self.assertFalse((self.root/"tampered").exists())
if __name__=="__main__":unittest.main()
