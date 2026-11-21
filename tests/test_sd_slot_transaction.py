from pathlib import Path

from openmenu_gdemu_manager.core.models import GameItem
from openmenu_gdemu_manager.services.sd_slot_transaction import (
    SdSlotTransactionService,
    incomplete_slot_transactions,
)


def _slot(root: Path, number: int, marker: str = "disc.gdi") -> Path:
    path = root / f"{number:02d}"
    path.mkdir(parents=True)
    (path / marker).write_text(f"slot {number}", encoding="ascii")
    return path


def _disc_with_product(folder: Path, product: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "disc.gdi").write_text(
        "\n".join(["1", "1 45000 4 2048 track03.iso 0"]),
        encoding="ascii",
    )
    ip = bytearray(0x100)
    ip[:16] = b"SEGA SEGAKATANA "
    ip[0x40:0x50] = product.encode("ascii").ljust(0x10, b" ")
    (folder / "track03.iso").write_bytes(bytes(ip))


def test_build_plan_compacts_sparse_slots():
    service = SdSlotTransactionService(Path("H:/"), "op")
    games = [GameItem(slot=2, name="A"), GameItem(slot=3, name="B"), GameItem(slot=5, name="C"), GameItem(slot=6, name="D")]

    plan = service.build_plan(games)

    assert [entry.to_dict() for entry in plan.moves] == [
        {"action": "move", "name": "C", "old_slot": 5, "new_slot": 4, "product_id": "", "source_path": "", "folder": "H:\\05"},
        {"action": "move", "name": "D", "old_slot": 6, "new_slot": 5, "product_id": "", "source_path": "", "folder": "H:\\06"},
    ]


def test_execute_deletes_to_internal_trash_and_compacts(tmp_path):
    root = tmp_path / "sd"
    slot2 = _slot(root, 2)
    slot3 = _slot(root, 3)
    slot4 = _slot(root, 4)
    games = [
        GameItem(slot=2, name="A", folder=slot2),
        GameItem(slot=3, name="B", folder=slot3, pending_delete=True),
        GameItem(slot=4, name="C", folder=slot4, product_id="SLOT004"),
    ]
    service = SdSlotTransactionService(root, "op-delete")
    plan = service.build_plan(games)

    result = service.execute(plan, games)

    assert (root / "_openmenu_gdemu_manager" / "trash" / "op-delete" / "03" / "disc.gdi").exists()
    assert (root / "03" / "disc.gdi").exists()
    assert not (root / "04").exists()
    assert games[2].slot == 3
    assert games[2].product_id == "SLOT003"
    assert result.moved[0]["old_slot"] == 4
    # Folders are final but menu 01 is not rebuilt yet: still recoverable.
    assert incomplete_slot_transactions(root) == [service.transaction_dir]
    service.mark_completed()
    assert incomplete_slot_transactions(root) == []


def _menu(root: Path, names: dict[int, str]) -> None:
    slot1 = root / "01"
    slot1.mkdir(parents=True, exist_ok=True)
    lines = ["[OPENMENU]", f"num_items={len(names)}", "[ITEMS]", "01.name=openMenu"]
    lines += [f"{slot:02d}.name={name}" for slot, name in sorted(names.items())]
    (slot1 / "track05.iso").write_bytes(b"pad" + "\n".join(lines).encode("latin-1") + b"\n" + b"\x00" * 64)


def _save_worker(monkeypatch, rebuilder):
    from openmenu_gdemu_manager.ui import workers
    monkeypatch.setattr(workers, "OpenMenuRebuilder", lambda: rebuilder)
    monkeypatch.setattr(workers, "write_openmenu_ini", lambda games: "")
    monkeypatch.setattr(workers, "patch_game_state", lambda state, root_path, game: None)
    monkeypatch.setattr(workers, "flush_state", lambda path, state: None)
    return workers


def _three_games(root: Path) -> list[GameItem]:
    return [
        GameItem(slot=2, name="A", folder=_slot(root, 2, "a.gdi")),
        GameItem(slot=3, name="B", folder=_slot(root, 3, "b.gdi"), pending_delete=True),
        GameItem(slot=4, name="C", folder=_slot(root, 4, "c.gdi"), product_id="T0004"),
    ]


def test_failed_menu_rebuild_keeps_transaction_recoverable_and_revert_restores_layout(tmp_path, monkeypatch):
    from openmenu_gdemu_manager.services.openmenu_rebuilder import OpenMenuRebuildError
    root = tmp_path / "sd"
    games = _three_games(root)
    _menu(root, {2: "A", 3: "B", 4: "C"})

    class Failing:
        def rebuild_and_replace(self, root_path, kept):
            raise OpenMenuRebuildError("buildgdi excedio el tiempo limite")

    workers = _save_worker(monkeypatch, Failing())
    errors: list[str] = []
    worker = workers.SaveChangesWorker(root, games, {}, write_allowed=True)
    worker.error.connect(errors.append)
    worker.run()

    assert errors and "buildgdi" in errors[0]
    assert (root / "03" / "c.gdi").exists() and not (root / "04").exists()
    [tx_dir] = incomplete_slot_transactions(root)
    service = SdSlotTransactionService(root, tx_dir.name)
    assert service.can_auto_recover()
    assert service.menu_out_of_date() and not service.can_complete_recovery()
    service.revert_from_state()
    assert [(root / f"{slot:02d}" / f"{name}.gdi").exists() for slot, name in ((2, "a"), (3, "b"), (4, "c"))] == [True] * 3
    assert incomplete_slot_transactions(root) == []


def test_successful_menu_rebuild_closes_transaction(tmp_path, monkeypatch):
    from types import SimpleNamespace
    root = tmp_path / "sd"
    games = _three_games(root)
    _menu(root, {2: "A", 3: "B", 4: "C"})

    class Working:
        def rebuild_and_replace(self, root_path, kept):
            return SimpleNamespace(num_items=len(kept), backup_slot=root / "backup")

    workers = _save_worker(monkeypatch, Working())
    errors: list[str] = []
    worker = workers.SaveChangesWorker(root, games, {}, write_allowed=True)
    worker.error.connect(errors.append)
    worker.run()

    assert errors == []
    assert incomplete_slot_transactions(root) == []


def test_menu_already_rebuilt_before_interruption_can_be_completed(tmp_path):
    root = tmp_path / "sd"
    games = _three_games(root)
    service = SdSlotTransactionService(root, "op-cut")
    service.execute(service.build_plan(games), games)
    # The swap of 01 finished but the app stopped before closing the transaction.
    _menu(root, {2: "A", 3: "C"})

    assert not service.menu_out_of_date() and service.can_complete_recovery()
    service.complete_from_state()
    assert incomplete_slot_transactions(root) == []
    assert (root / "03" / "c.gdi").exists()


def test_delete_and_add_in_one_save_produces_a_recoverable_plan(tmp_path):
    from openmenu_gdemu_manager.services.game_service import next_free_slot
    root = tmp_path / "sd"
    games = _three_games(root)
    source = tmp_path / "new_game"
    source.mkdir()
    (source / "disc.cdi").write_text("new", encoding="ascii")
    slot = next_free_slot(games)
    assert slot == 5
    games.append(GameItem(slot=slot, name="D", source_path=source, pending_add=True))
    service = SdSlotTransactionService(root, "op-replace")
    plan = service.build_plan(games)

    service._validate_plan_entries(plan)
    assert [(e.action, e.old_slot, e.new_slot) for e in plan.entries] == [
        ("keep", 2, 2), ("delete", 3, None), ("move", 4, 3), ("add", 5, 4)]
    service.execute(plan, games)
    assert service.can_auto_recover()
    assert (root / "04" / "disc.cdi").exists() and (root / "03" / "c.gdi").exists()


def test_colliding_plan_is_rejected_before_touching_the_sd(tmp_path):
    import pytest
    root = tmp_path / "sd"
    games = _three_games(root)
    source = tmp_path / "new_game"
    source.mkdir()
    (source / "disc.cdi").write_text("new", encoding="ascii")
    games.append(GameItem(slot=3, name="D", source_path=source, pending_add=True))
    service = SdSlotTransactionService(root, "op-collide")

    with pytest.raises(ValueError, match="Invalid original slot"):
        service.execute(service.build_plan(games), games)
    assert not service.transaction_dir.exists()
    assert (root / "03" / "b.gdi").exists() and (root / "04" / "c.gdi").exists()


def test_execute_adds_from_temporary_copy(tmp_path):
    root = tmp_path / "sd"
    slot2 = _slot(root, 2)
    source = tmp_path / "source_game"
    source.mkdir()
    (source / "disc.cdi").write_text("new game", encoding="ascii")
    games = [
        GameItem(slot=2, name="A", folder=slot2),
        GameItem(slot=3, name="New", source_path=str(source), pending_add=True, is_new=True, product_id="SLOT003"),
    ]
    service = SdSlotTransactionService(root, "op-add")

    result = service.execute(service.build_plan(games), games)

    assert (root / "03" / "disc.cdi").read_text(encoding="ascii") == "new game"
    assert not games[1].pending_add
    assert result.added[0]["new_slot"] == 3


def test_execute_add_uses_real_disc_product_before_rebuilding_menu(tmp_path):
    root = tmp_path / "sd"
    slot2 = _slot(root, 2)
    source = tmp_path / "source_game"
    _disc_with_product(source, "MK51033")
    games = [
        GameItem(slot=2, name="A", folder=slot2),
        GameItem(slot=3, name="Ecco", source_path=str(source), pending_add=True, is_new=True, product_id="SLOT030"),
    ]
    service = SdSlotTransactionService(root, "op-add-product")

    result = service.execute(service.build_plan(games), games)

    assert games[1].product_id == "MK51033"
    assert games[1].artwork_serials == ["SLOT030", "SLOT003", "MK51033"]
    assert result.product_updates == [
        {
            "old_slot": 3,
            "new_slot": 3,
            "name": "Ecco",
            "old_product_id": "SLOT030",
            "new_product_id": "MK51033",
            "artwork_aliases": ["SLOT030", "SLOT003", "MK51033"],
        }
    ]


def test_execute_reorders_without_slot_collisions(tmp_path):
    root = tmp_path / "sd"
    slot2 = _slot(root, 2)
    slot3 = _slot(root, 3)
    games = [
        GameItem(slot=3, name="B", folder=slot3),
        GameItem(slot=2, name="A", folder=slot2),
    ]
    service = SdSlotTransactionService(root, "op-reorder")

    service.execute(service.build_plan(games), games)

    assert (root / "02" / "disc.gdi").read_text(encoding="ascii") == "slot 3"
    assert (root / "03" / "disc.gdi").read_text(encoding="ascii") == "slot 2"
    assert [game.slot for game in games] == [2, 3]


def test_revert_from_state_restores_temp_and_trash(tmp_path):
    root = tmp_path / "sd"
    slot2 = _slot(root, 2)
    slot3 = _slot(root, 3)
    games = [
        GameItem(slot=2, name="A", folder=slot2, pending_delete=True),
        GameItem(slot=3, name="B", folder=slot3),
    ]
    service = SdSlotTransactionService(root, "op-revert")
    plan = service.build_plan(games)
    service.transaction_dir.mkdir(parents=True)
    service._write_json("plan.json", plan.to_dict())
    service.trash_dir.mkdir(parents=True)
    slot2.rename(service.trash_dir / "02")
    service.temp_dir.mkdir(parents=True)
    slot3.rename(service.temp_dir / "03")
    service._write_state("moved_to_temp")

    assert incomplete_slot_transactions(root) == [service.transaction_dir]
    service.revert_from_state()

    assert (root / "02" / "disc.gdi").exists()
    assert (root / "03" / "disc.gdi").exists()
    assert incomplete_slot_transactions(root) == []


def test_incomplete_transactions_detect_missing_or_corrupt_state(tmp_path):
    root = tmp_path / "sd"
    base = root / "_openmenu_gdemu_manager" / "slot_transactions"
    missing_state = base / "tx-missing"
    corrupt_state = base / "tx-corrupt"
    completed_state = base / "tx-completed"
    missing_state.mkdir(parents=True)
    corrupt_state.mkdir(parents=True)
    completed_state.mkdir(parents=True)
    (corrupt_state / "state.json").write_text("{broken", encoding="utf-8")
    (completed_state / "state.json").write_text('{"stage":"completed"}', encoding="utf-8")

    pending = incomplete_slot_transactions(root)

    assert missing_state in pending
    assert corrupt_state in pending
    assert completed_state not in pending


def test_revert_does_not_delete_untracked_final_slot(tmp_path):
    root = tmp_path / "sd"
    service = SdSlotTransactionService(root, "op-revert-safe")
    source = tmp_path / "src"
    source.mkdir(parents=True)
    (source / "disc.cdi").write_text("payload", encoding="ascii")
    existing_target = _slot(root, 2)
    game = GameItem(slot=2, name="New", source_path=str(source), pending_add=True, is_new=True, product_id="SLOT002")
    plan = service.build_plan([game])
    service.transaction_dir.mkdir(parents=True, exist_ok=True)
    service._write_json("plan.json", plan.to_dict())
    service._write_state("moved_to_final", created_slots=[])
    assert (existing_target / "disc.gdi").exists()

    service.revert_from_state()

    assert (existing_target / "disc.gdi").exists()


def test_state_writer_produces_valid_json(tmp_path):
    root = tmp_path / "sd"
    service = SdSlotTransactionService(root, "op-state")
    service.transaction_dir.mkdir(parents=True, exist_ok=True)

    service._write_state("planned", foo="bar")

    data = (service.transaction_dir / "state.json").read_text(encoding="utf-8")
    assert '"stage": "planned"' in data
    assert '"foo": "bar"' in data
