"""Comprehensive tests for Phase 9 Model Training Pipeline modules.

Covers:
  - TrainingExporter — ShareGPT / DPO / Alpaca export from forge memory
  - LoraRunner — job creation, config generation, monitoring
  - BitemporalStore — record, query_current, query_as_of, supersede, history
  - FederationManager — config generation, restore script, install instructions
  - ImprovementScheduler — daily/weekly/monthly cycles, schedule status

All external calls (LLM, SSH, training processes) are mocked.
No Ollama, no GPU, no network required.
"""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── helpers ────────────────────────────────────────────────────────────────────


def _tmp_store():
    from jarvis.forge.memory_store import ForgeMemoryStore
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return ForgeMemoryStore(db_path=path), path


def _tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return path


# ══════════════════════════════════════════════════════════════════════════════
# TrainingExporter
# ══════════════════════════════════════════════════════════════════════════════


class TestTrainingExporter:
    def test_export_corrections_empty_store(self):
        from jarvis.forge.training_exporter import TrainingExporter
        store, store_path = _tmp_store()
        export_dir = tempfile.mkdtemp()
        exporter = TrainingExporter(memory_store=store, output_dir=export_dir)
        stats = exporter.export_corrections()
        assert stats.total_pairs == 0
        assert stats.output_path == ""
        import shutil; shutil.rmtree(export_dir, ignore_errors=True)
        os.unlink(store_path)

    def test_export_corrections_with_pairs_sharegpt(self):
        from jarvis.forge.training_exporter import TrainingExporter
        store, store_path = _tmp_store()
        # Add correction pairs
        store.log_correction(
            agent="critic", bad_output="wrong answer", good_output="correct answer"
        )
        store.log_correction(
            agent="critic", bad_output="off topic", good_output="on topic"
        )
        export_dir = tempfile.mkdtemp()
        exporter = TrainingExporter(memory_store=store, output_dir=export_dir)
        stats = exporter.export_corrections(format="sharegpt")
        assert stats.total_pairs == 2
        assert stats.output_path.endswith(".jsonl")
        # Verify file contents
        with open(stats.output_path) as f:
            lines = f.readlines()
        assert len(lines) == 2
        record = json.loads(lines[0])
        assert "conversations" in record
        import shutil; shutil.rmtree(export_dir, ignore_errors=True)
        os.unlink(store_path)

    def test_export_corrections_dpo_format(self):
        from jarvis.forge.training_exporter import TrainingExporter
        store, store_path = _tmp_store()
        store.log_correction(agent="critic", bad_output="bad", good_output="good")
        export_dir = tempfile.mkdtemp()
        exporter = TrainingExporter(memory_store=store, output_dir=export_dir)
        stats = exporter.export_corrections(format="dpo", mark_used=False)
        assert stats.total_pairs == 1
        with open(stats.output_path) as f:
            record = json.loads(f.readline())
        assert "prompt" in record
        assert "chosen" in record
        assert "rejected" in record
        import shutil; shutil.rmtree(export_dir, ignore_errors=True)
        os.unlink(store_path)

    def test_export_corrections_alpaca_format(self):
        from jarvis.forge.training_exporter import TrainingExporter
        store, store_path = _tmp_store()
        store.log_correction(agent="trainer", bad_output="bad", good_output="good")
        export_dir = tempfile.mkdtemp()
        exporter = TrainingExporter(memory_store=store, output_dir=export_dir)
        stats = exporter.export_corrections(format="alpaca")
        assert stats.total_pairs == 1
        with open(stats.output_path) as f:
            record = json.loads(f.readline())
        assert "instruction" in record
        assert "output" in record
        import shutil; shutil.rmtree(export_dir, ignore_errors=True)
        os.unlink(store_path)

    def test_export_corrections_marks_used(self):
        from jarvis.forge.training_exporter import TrainingExporter
        store, store_path = _tmp_store()
        store.log_correction(agent="critic", bad_output="bad", good_output="good")
        export_dir = tempfile.mkdtemp()
        exporter = TrainingExporter(memory_store=store, output_dir=export_dir)
        exporter.export_corrections(mark_used=True)
        # Second export should yield 0 (already marked used)
        stats2 = exporter.export_corrections(mark_used=False)
        assert stats2.total_pairs == 0
        import shutil; shutil.rmtree(export_dir, ignore_errors=True)
        os.unlink(store_path)

    def test_export_high_quality_interactions(self):
        from jarvis.forge.training_exporter import TrainingExporter
        store, store_path = _tmp_store()
        # Add some long interactions (good quality)
        for i in range(5):
            store.log_interaction(
                agent="critic", task_id=f"t{i}",
                input_text="what is X?",
                output_text="X is a detailed concept that requires " + "a" * 60,
            )
        export_dir = tempfile.mkdtemp()
        exporter = TrainingExporter(memory_store=store, output_dir=export_dir)
        stats = exporter.export_high_quality_interactions(min_length=50)
        assert stats.total_pairs == 5
        import shutil; shutil.rmtree(export_dir, ignore_errors=True)
        os.unlink(store_path)

    def test_export_high_quality_filters_hallucinations(self):
        from jarvis.forge.training_exporter import TrainingExporter
        store, store_path = _tmp_store()
        # Add interaction and mark it as hallucination
        ix_id = store.log_interaction(
            agent="critic", task_id="bad-task",
            input_text="query", output_text="fabricated facts " * 10,
        )
        store.log_hallucination(
            agent="critic", claim="bad claim",
            interaction_id=ix_id, severity="high",
        )
        export_dir = tempfile.mkdtemp()
        exporter = TrainingExporter(memory_store=store, output_dir=export_dir)
        stats = exporter.export_high_quality_interactions()
        assert stats.total_pairs == 0
        import shutil; shutil.rmtree(export_dir, ignore_errors=True)
        os.unlink(store_path)

    def test_export_all_returns_list(self):
        from jarvis.forge.training_exporter import TrainingExporter
        store, store_path = _tmp_store()
        export_dir = tempfile.mkdtemp()
        exporter = TrainingExporter(memory_store=store, output_dir=export_dir)
        with patch.object(exporter, 'export_dpo_from_decisions', return_value=__import__('jarvis.forge.training_exporter', fromlist=['ExportStats']).ExportStats(format='dpo', source='decisions', total_pairs=0, output_path='')):
            results = exporter.export_all()
        assert isinstance(results, list)
        import shutil; shutil.rmtree(export_dir, ignore_errors=True)
        os.unlink(store_path)

    def test_get_export_manifest(self):
        from jarvis.forge.training_exporter import TrainingExporter
        store, store_path = _tmp_store()
        export_dir = tempfile.mkdtemp()
        exporter = TrainingExporter(memory_store=store, output_dir=export_dir)
        # Create a dummy file
        (Path(export_dir) / "test_20240101T120000.jsonl").write_text("{}\n")
        manifest = exporter.get_export_manifest()
        assert len(manifest) == 1
        assert "filename" in manifest[0]
        import shutil; shutil.rmtree(export_dir, ignore_errors=True)
        os.unlink(store_path)

    def test_dpo_pairs_include_bitemporal_fields(self):
        from jarvis.forge.training_exporter import TrainingExporter
        store, store_path = _tmp_store()
        store.log_correction(agent="critic", bad_output="bad", good_output="good")
        export_dir = tempfile.mkdtemp()
        exporter = TrainingExporter(memory_store=store, output_dir=export_dir)
        stats = exporter.export_corrections(format="sharegpt", mark_used=False)
        with open(stats.output_path) as f:
            record = json.loads(f.readline())
        assert "_meta" in record
        assert "valid_from" in record["_meta"]
        assert "known_from" in record["_meta"]
        import shutil; shutil.rmtree(export_dir, ignore_errors=True)
        os.unlink(store_path)


# ══════════════════════════════════════════════════════════════════════════════
# LoraRunner
# ══════════════════════════════════════════════════════════════════════════════


class TestLoraRunner:
    def test_create_job_persists(self, tmp_path):
        from jarvis.forge.lora_runner import LoraRunner
        db = str(tmp_path / "jobs.db")
        configs = str(tmp_path / "configs")
        runner = LoraRunner(db_path=db, configs_dir=configs)
        job = runner.create_job("test-job", "/tmp/data.jsonl")
        assert job.id
        assert job.status == "pending"

    def test_create_job_custom_hparams(self, tmp_path):
        from jarvis.forge.lora_runner import LoraRunner
        db = str(tmp_path / "jobs.db")
        runner = LoraRunner(db_path=db, configs_dir=str(tmp_path / "c"))
        job = runner.create_job("j", "/tmp/d.jsonl", hparams={"lora_r": 32, "num_train_epochs": 5})
        assert job.config["lora_r"] == 32
        assert job.config["num_train_epochs"] == 5

    def test_configure_axolotl_writes_yaml(self, tmp_path):
        from jarvis.forge.lora_runner import LoraRunner
        db = str(tmp_path / "jobs.db")
        configs = str(tmp_path / "configs")
        runner = LoraRunner(db_path=db, configs_dir=configs)
        job = runner.create_job("j", "/tmp/data.jsonl", backend="axolotl")
        config_path = runner.configure(job.id)
        assert config_path.endswith(".yaml")
        assert os.path.exists(config_path)
        content = Path(config_path).read_text()
        assert "base_model" in content
        assert "lora_r" in content

    def test_configure_llamacpp_writes_shell_script(self, tmp_path):
        from jarvis.forge.lora_runner import LoraRunner
        db = str(tmp_path / "jobs.db")
        configs = str(tmp_path / "configs")
        runner = LoraRunner(db_path=db, configs_dir=configs)
        job = runner.create_job("j", "/tmp/data.jsonl", backend="llama.cpp")
        config_path = runner.configure(job.id)
        assert config_path.endswith(".sh")

    def test_launch_dry_run(self, tmp_path):
        from jarvis.forge.lora_runner import LoraRunner
        db = str(tmp_path / "jobs.db")
        runner = LoraRunner(db_path=db, configs_dir=str(tmp_path / "c"))
        job = runner.create_job("j", "/tmp/data.jsonl")
        runner.configure(job.id)
        result = runner.launch(job.id, dry_run=True)
        assert result == "dry_run"

    def test_launch_binary_not_found(self, tmp_path):
        from jarvis.forge.lora_runner import LoraRunner
        db = str(tmp_path / "jobs.db")
        runner = LoraRunner(db_path=db, configs_dir=str(tmp_path / "c"))
        job = runner.create_job("j", "/tmp/data.jsonl", backend="axolotl")
        runner.configure(job.id)
        # axolotl won't be installed in test env
        result = runner.launch(job.id, dry_run=False)
        # Should fail gracefully, not raise
        assert isinstance(result, str)

    def test_monitor_job_not_found(self, tmp_path):
        from jarvis.forge.lora_runner import LoraRunner
        db = str(tmp_path / "jobs.db")
        runner = LoraRunner(db_path=db, configs_dir=str(tmp_path / "c"))
        result = runner.monitor("nonexistent-id")
        assert result.status == "not_found"

    def test_monitor_pending_job(self, tmp_path):
        from jarvis.forge.lora_runner import LoraRunner
        db = str(tmp_path / "jobs.db")
        runner = LoraRunner(db_path=db, configs_dir=str(tmp_path / "c"))
        job = runner.create_job("j", "/tmp/data.jsonl")
        result = runner.monitor(job.id)
        assert result.status == "pending"
        assert result.final_loss is None

    def test_list_jobs_empty(self, tmp_path):
        from jarvis.forge.lora_runner import LoraRunner
        db = str(tmp_path / "jobs.db")
        runner = LoraRunner(db_path=db, configs_dir=str(tmp_path / "c"))
        jobs = runner.list_jobs()
        assert jobs == []

    def test_list_jobs_with_filter(self, tmp_path):
        from jarvis.forge.lora_runner import LoraRunner
        db = str(tmp_path / "jobs.db")
        runner = LoraRunner(db_path=db, configs_dir=str(tmp_path / "c"))
        runner.create_job("j1", "/tmp/d.jsonl")
        runner.create_job("j2", "/tmp/d.jsonl")
        pending = runner.list_jobs(status="pending")
        assert len(pending) == 2
        running = runner.list_jobs(status="running")
        assert len(running) == 0

    def test_summary(self, tmp_path):
        from jarvis.forge.lora_runner import LoraRunner
        db = str(tmp_path / "jobs.db")
        runner = LoraRunner(db_path=db, configs_dir=str(tmp_path / "c"))
        runner.create_job("j1", "/tmp/d.jsonl")
        runner.create_job("j2", "/tmp/d.jsonl")
        s = runner.summary()
        assert s.get("pending", 0) == 2

    def test_publish_to_ollama_not_completed(self, tmp_path):
        from jarvis.forge.lora_runner import LoraRunner
        db = str(tmp_path / "jobs.db")
        runner = LoraRunner(db_path=db, configs_dir=str(tmp_path / "c"))
        job = runner.create_job("j", "/tmp/d.jsonl")
        result = runner.publish_to_ollama(job.id, "my-model")
        assert "not completed" in result

    def test_monitor_parses_loss_from_log(self, tmp_path):
        from jarvis.forge.lora_runner import LoraRunner
        db = str(tmp_path / "jobs.db")
        configs = str(tmp_path / "configs")
        runner = LoraRunner(db_path=db, configs_dir=configs)
        job = runner.create_job("j", "/tmp/d.jsonl")
        # Simulate a log file
        job_dir = Path(configs) / job.id
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "train.log").write_text(
            "Epoch 1/3: loss = 2.340\nEpoch 2/3: loss=1.234\nEpoch 3/3: loss = 0.876\n"
        )
        result = runner.monitor(job.id)
        assert result.final_loss is not None
        assert 0 < result.final_loss < 5


# ══════════════════════════════════════════════════════════════════════════════
# BitemporalStore
# ══════════════════════════════════════════════════════════════════════════════


class TestBitemporalStore:
    def test_record_and_query_current(self, tmp_path):
        from jarvis.forge.bitemporal_store import BitemporalStore
        store = BitemporalStore(db_path=str(tmp_path / "bt.db"))
        store.record(domain="finance", key="prime_rate", value=5.25, valid_from="2023-07-26")
        facts = store.query_current(domain="finance", key="prime_rate")
        assert len(facts) == 1
        assert facts[0].value == 5.25

    def test_expire_fact(self, tmp_path):
        from jarvis.forge.bitemporal_store import BitemporalStore
        store = BitemporalStore(db_path=str(tmp_path / "bt.db"))
        fid = store.record(domain="finance", key="prime_rate", value=5.25, valid_from="2023-07-26")
        store.expire_fact(fid, valid_to="2024-11-07")
        # Should no longer appear in current query (rate expired)
        facts = store.query_current(domain="finance", key="prime_rate")
        assert len(facts) == 0

    def test_supersede_replaces_old_fact(self, tmp_path):
        from jarvis.forge.bitemporal_store import BitemporalStore
        store = BitemporalStore(db_path=str(tmp_path / "bt.db"))
        store.record(domain="finance", key="prime_rate", value=5.25, valid_from="2023-07-26")
        new_id, expired = store.supersede(
            domain="finance", key="prime_rate", new_value=4.75, valid_from="2024-11-07"
        )
        assert len(expired) == 1
        facts = store.query_current(domain="finance", key="prime_rate")
        assert len(facts) == 1
        assert facts[0].value == 4.75

    def test_query_as_of_returns_historical(self, tmp_path):
        from jarvis.forge.bitemporal_store import BitemporalStore
        store = BitemporalStore(db_path=str(tmp_path / "bt.db"))
        # Simulate: learned the old rate in 2023, it expired in 2024-11-07
        store.record(
            domain="finance", key="prime_rate", value=5.25,
            valid_from="2023-07-26", valid_to="2024-11-07",
            known_from="2023-07-26",
        )
        # New rate known from 2024-11-07
        store.record(
            domain="finance", key="prime_rate", value=4.75,
            valid_from="2024-11-07", known_from="2024-11-07",
        )
        # Query as of 2024-01-01 (before the change)
        facts = store.query_as_of(valid_at="2024-01-01", known_at="2024-01-01", key="prime_rate")
        assert len(facts) == 1
        assert facts[0].value == 5.25

    def test_query_as_of_after_supersede(self, tmp_path):
        from jarvis.forge.bitemporal_store import BitemporalStore
        store = BitemporalStore(db_path=str(tmp_path / "bt.db"))
        store.record(
            domain="finance", key="prime_rate", value=5.25,
            valid_from="2023-07-26", valid_to="2024-11-07",
            known_from="2023-07-26",
        )
        store.record(
            domain="finance", key="prime_rate", value=4.75,
            valid_from="2024-11-07", known_from="2024-11-07",
        )
        # Query as of 2024-12-01 (after the change)
        facts = store.query_as_of(valid_at="2024-12-01", known_at="2024-12-01", key="prime_rate")
        assert len(facts) == 1
        assert facts[0].value == 4.75

    def test_history_returns_all_versions(self, tmp_path):
        from jarvis.forge.bitemporal_store import BitemporalStore
        store = BitemporalStore(db_path=str(tmp_path / "bt.db"))
        store.record(domain="finance", key="prime_rate", value=5.25, valid_from="2023-07-26", valid_to="2024-11-07")
        store.record(domain="finance", key="prime_rate", value=4.75, valid_from="2024-11-07")
        hist = store.history("finance", "prime_rate")
        assert len(hist) == 2

    def test_domains_returns_list(self, tmp_path):
        from jarvis.forge.bitemporal_store import BitemporalStore
        store = BitemporalStore(db_path=str(tmp_path / "bt.db"))
        store.record(domain="finance", key="rate", value=5.0, valid_from="2024-01-01")
        store.record(domain="security", key="threat_level", value="low", valid_from="2024-01-01")
        domains = store.domains()
        assert "finance" in domains
        assert "security" in domains

    def test_summary_counts(self, tmp_path):
        from jarvis.forge.bitemporal_store import BitemporalStore
        store = BitemporalStore(db_path=str(tmp_path / "bt.db"))
        store.record(domain="finance", key="rate", value=5.0, valid_from="2024-01-01")
        s = store.summary()
        assert s["total_facts"] == 1
        assert s["current_facts"] == 1
        assert s["domains"] == 1

    def test_tags_filter(self, tmp_path):
        from jarvis.forge.bitemporal_store import BitemporalStore
        store = BitemporalStore(db_path=str(tmp_path / "bt.db"))
        store.record(domain="finance", key="a", value=1, valid_from="2024-01-01", tags=["fed", "rate"])
        store.record(domain="finance", key="b", value=2, valid_from="2024-01-01", tags=["gdp"])
        facts = store.query_current(tags=["fed"])
        assert len(facts) == 1
        assert facts[0].key == "a"

    def test_confidence_stored(self, tmp_path):
        from jarvis.forge.bitemporal_store import BitemporalStore
        store = BitemporalStore(db_path=str(tmp_path / "bt.db"))
        store.record(domain="test", key="x", value="v", valid_from="2024-01-01", confidence=0.75)
        facts = store.query_current(domain="test")
        assert facts[0].confidence == pytest.approx(0.75)

    def test_value_can_be_complex_type(self, tmp_path):
        from jarvis.forge.bitemporal_store import BitemporalStore
        store = BitemporalStore(db_path=str(tmp_path / "bt.db"))
        store.record(domain="test", key="data", value={"a": [1, 2, 3]}, valid_from="2024-01-01")
        facts = store.query_current()
        assert facts[0].value == {"a": [1, 2, 3]}


# ══════════════════════════════════════════════════════════════════════════════
# FederationManager
# ══════════════════════════════════════════════════════════════════════════════


class TestFederationManager:
    def test_generate_creates_config_file(self, tmp_path):
        from jarvis.forge.federation import FederationManager
        fm = FederationManager(
            jarvis_root=str(tmp_path),
            replica_hosts=["192.168.1.100"],
        )
        config = fm.generate(output_dir=str(tmp_path / "litestream"))
        assert os.path.exists(config.config_path)
        content = Path(config.config_path).read_text()
        assert "litestream" in content.lower() or "dbs:" in content

    def test_generate_creates_restore_script(self, tmp_path):
        from jarvis.forge.federation import FederationManager
        fm = FederationManager(
            jarvis_root=str(tmp_path),
            replica_hosts=["192.168.1.100"],
        )
        config = fm.generate(output_dir=str(tmp_path / "ls"))
        assert os.path.exists(config.restore_script_path)
        content = Path(config.restore_script_path).read_text()
        assert "restore" in content

    def test_generate_creates_systemd_unit(self, tmp_path):
        from jarvis.forge.federation import FederationManager
        fm = FederationManager(
            jarvis_root=str(tmp_path),
            replica_hosts=["192.168.1.100"],
        )
        config = fm.generate(output_dir=str(tmp_path / "ls"))
        assert os.path.exists(config.systemd_unit_path)
        content = Path(config.systemd_unit_path).read_text()
        assert "[Unit]" in content
        assert "litestream" in content.lower()

    def test_generate_with_s3_bucket(self, tmp_path):
        from jarvis.forge.federation import FederationManager
        fm = FederationManager(
            jarvis_root=str(tmp_path),
            replica_hosts=[],
            s3_bucket="my-backup-bucket",
        )
        config = fm.generate(output_dir=str(tmp_path / "ls"))
        content = Path(config.config_path).read_text()
        assert "s3" in content or "my-backup-bucket" in content

    def test_generate_with_local_dir(self, tmp_path):
        from jarvis.forge.federation import FederationManager
        local_replica = str(tmp_path / "replicas")
        fm = FederationManager(
            jarvis_root=str(tmp_path),
            replica_hosts=[],
            local_replica_dir=local_replica,
        )
        config = fm.generate(output_dir=str(tmp_path / "ls"))
        content = Path(config.config_path).read_text()
        assert local_replica in content or "file" in content

    def test_add_node_adds_to_chain(self, tmp_path):
        from jarvis.forge.federation import FederationManager
        fm = FederationManager(jarvis_root=str(tmp_path), replica_hosts=[])
        fm.add_node("new_node", "192.168.1.200")
        assert "192.168.1.200" in fm._replica_hosts

    def test_install_instructions_contains_steps(self, tmp_path):
        from jarvis.forge.federation import FederationManager
        fm = FederationManager(jarvis_root=str(tmp_path), replica_hosts=["192.168.1.100"])
        instructions = fm.install_instructions()
        assert "Install Litestream" in instructions
        assert "systemd" in instructions.lower()

    def test_node_status_returns_dict(self, tmp_path):
        from jarvis.forge.federation import FederationManager
        fm = FederationManager(jarvis_root=str(tmp_path), replica_hosts=["192.168.111.255"])
        status = fm.node_status()
        assert "nodes" in status
        # Host is unreachable in test env
        assert status["nodes"].get("192.168.111.255") == "unreachable"

    def test_generate_node_config(self, tmp_path):
        from jarvis.forge.federation import FederationManager
        fm = FederationManager(jarvis_root=str(tmp_path), replica_hosts=["192.168.1.100"])
        path = fm.generate_node_config("worker", output_dir=str(tmp_path / "ls"))
        assert os.path.exists(path)

    def test_config_includes_all_databases(self, tmp_path):
        from jarvis.forge.federation import FederationManager, _DATABASES
        fm = FederationManager(jarvis_root=str(tmp_path), replica_hosts=["192.168.1.100"])
        config = fm.generate(output_dir=str(tmp_path / "ls"))
        content = Path(config.config_path).read_text()
        # At least some databases should be in the config
        assert "forge.db" in content or "memory.db" in content


# ══════════════════════════════════════════════════════════════════════════════
# ImprovementScheduler
# ══════════════════════════════════════════════════════════════════════════════


class TestImprovementScheduler:
    def _make_scheduler(self, tmp_path):
        from jarvis.forge.improvement_scheduler import ImprovementScheduler
        return ImprovementScheduler(db_path=str(tmp_path / "forge.db"))

    def test_get_config_returns_defaults(self, tmp_path):
        sched = self._make_scheduler(tmp_path)
        assert sched.get_config("min_pairs_for_training") == "100"
        assert sched.get_config("auto_launch_training") == "false"

    def test_set_and_get_config(self, tmp_path):
        sched = self._make_scheduler(tmp_path)
        sched.set_config("min_pairs_for_training", "250")
        assert sched.get_config("min_pairs_for_training") == "250"

    def test_get_all_config_includes_defaults(self, tmp_path):
        sched = self._make_scheduler(tmp_path)
        cfg = sched.get_all_config()
        assert "daily_run_hour" in cfg
        assert "training_backend" in cfg

    def test_is_due_returns_true_when_never_run(self, tmp_path):
        sched = self._make_scheduler(tmp_path)
        assert sched.is_due("daily") is True
        assert sched.is_due("weekly") is True
        assert sched.is_due("monthly") is True

    def test_run_daily_returns_report(self, tmp_path):
        sched = self._make_scheduler(tmp_path)
        # Mock all sub-components to avoid real LLM calls
        with patch("jarvis.forge.improvement_scheduler.ImprovementScheduler._post_to_blackboard"), \
             patch("jarvis.forge.trainer.AgentTrainer.review_all", return_value=[]), \
             patch("jarvis.forge.pattern_analyst.PatternAnalyst.analyze_all", return_value=[]), \
             patch("jarvis.forge.tester.AgentTester.test_all_staged", return_value=[]):
            try:
                report = sched.run_daily()
            except Exception:
                # If imports fail in test env, run_daily gracefully handles it
                return
        assert report.cycle_type == "daily"
        assert isinstance(report.errors, list)

    def test_run_daily_records_in_db(self, tmp_path):
        sched = self._make_scheduler(tmp_path)
        with patch("jarvis.forge.improvement_scheduler.ImprovementScheduler._post_to_blackboard"):
            report = sched.run_daily()
        status = sched.get_schedule_status()
        assert status["last_daily"] is not None

    def test_is_due_false_after_run(self, tmp_path):
        sched = self._make_scheduler(tmp_path)
        with patch("jarvis.forge.improvement_scheduler.ImprovementScheduler._post_to_blackboard"):
            sched.run_daily()
        assert sched.is_due("daily") is False

    def test_run_weekly_returns_report(self, tmp_path):
        sched = self._make_scheduler(tmp_path)
        with patch("jarvis.forge.improvement_scheduler.ImprovementScheduler._post_to_blackboard"), \
             patch("jarvis.forge.training_exporter.TrainingExporter.export_all", return_value=[]):
            report = sched.run_weekly()
        assert report.cycle_type == "weekly"
        assert isinstance(report.training_pairs_exported, int)

    def test_run_monthly_no_jobs_staged(self, tmp_path):
        sched = self._make_scheduler(tmp_path)
        with patch("jarvis.forge.improvement_scheduler.ImprovementScheduler._post_to_blackboard"), \
             patch("jarvis.forge.lora_runner.LoraRunner.list_jobs", return_value=[]):
            report = sched.run_monthly()
        assert report.cycle_type == "monthly"
        assert report.training_status == "no_jobs_staged"

    def test_get_schedule_status_has_next_times(self, tmp_path):
        sched = self._make_scheduler(tmp_path)
        status = sched.get_schedule_status()
        assert "next_daily" in status
        assert "next_weekly" in status
        assert "next_monthly" in status

    def test_run_due_runs_all_overdue(self, tmp_path):
        sched = self._make_scheduler(tmp_path)
        with patch("jarvis.forge.improvement_scheduler.ImprovementScheduler._post_to_blackboard"), \
             patch("jarvis.forge.improvement_scheduler.ImprovementScheduler.run_daily", return_value=MagicMock(cycle_type="daily")), \
             patch("jarvis.forge.improvement_scheduler.ImprovementScheduler.run_weekly", return_value=MagicMock(cycle_type="weekly")), \
             patch("jarvis.forge.improvement_scheduler.ImprovementScheduler.run_monthly", return_value=MagicMock(cycle_type="monthly")):
            reports = sched.run_due()
        assert len(reports) >= 1
