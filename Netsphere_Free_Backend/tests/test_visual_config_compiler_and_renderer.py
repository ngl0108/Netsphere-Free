from app.services.visual_config_compiler import compile_graph_to_ir
from app.services.visual_config_renderer import render_ir_to_commands, render_ir_to_rollback_commands


def test_compile_and_render_cisco_like_preview():
    graph = {
        "nodes": [
            {"id": "t1", "type": "target", "data": {"target_type": "devices", "device_ids": [1]}},
            {"id": "v1", "type": "vlan", "data": {"vlan_id": 10, "name": "Users"}},
            {"id": "i1", "type": "interface", "data": {"ports": "Gi1/0/1", "admin_state": "up", "mode": "access", "access_vlan": 10}},
        ],
        "edges": [],
    }
    c = compile_graph_to_ir(graph)
    assert not c.errors
    assert not c.errors_by_node_id
    cmds = render_ir_to_commands(c.ir, "cisco_ios")
    assert "vlan 10" in cmds
    assert " switchport access vlan 10" in cmds

    rb = render_ir_to_rollback_commands(c.ir, "cisco_ios")
    assert "no vlan 10" in rb


def test_compile_and_render_domestic_vendor_preview():
    graph = {
        "nodes": [
            {"id": "t1", "type": "target", "data": {"target_type": "devices", "device_ids": [1]}},
            {"id": "v1", "type": "vlan", "data": {"vlan_id": 20, "name": "Korea", "svi_ip": "10.20.0.1/24"}},
            {"id": "i1", "type": "interface", "data": {"ports": "Gi1/0/2", "admin_state": "up", "mode": "access", "access_vlan": 20}},
        ],
        "edges": [],
    }
    c = compile_graph_to_ir(graph)
    assert not c.errors
    cmds = render_ir_to_commands(c.ir, "dasan_nos")
    assert "vlan 20" in cmds
    assert "interface vlan 20" in cmds
    assert " switchport access vlan 20" in cmds

    rb = render_ir_to_rollback_commands(c.ir, "dasan_nos")
    assert "no vlan 20" in rb


def test_compile_and_render_ubiquoss_preview():
    graph = {
        "nodes": [
            {"id": "t1", "type": "target", "data": {"target_type": "devices", "device_ids": [1]}},
            {"id": "v1", "type": "vlan", "data": {"vlan_id": 30, "name": "UQ", "svi_ip": "10.30.0.1/24"}},
            {"id": "i1", "type": "interface", "data": {"ports": "Gi1/0/3", "admin_state": "up", "mode": "trunk", "native_vlan": 1, "allowed_vlans": "10,20,30"}},
            {"id": "l1", "type": "l2_safety", "data": {"ports": "Gi1/0/3", "portfast": True, "bpduguard": True}},
        ],
        "edges": [],
    }
    c = compile_graph_to_ir(graph)
    assert not c.errors
    cmds = render_ir_to_commands(c.ir, "ubiquoss_l2")
    assert "interface vlan 30" in cmds
    assert " switchport trunk allowed vlan add 10,20,30" in cmds
    assert " spanning-tree portfast edge" in cmds
    assert " spanning-tree bpduguard" in cmds

    rb = render_ir_to_rollback_commands(c.ir, "ubiquoss_l2")
    assert "no vlan 30" in rb


def test_compile_and_render_handream_preview():
    graph = {
        "nodes": [
            {"id": "t1", "type": "target", "data": {"target_type": "devices", "device_ids": [1]}},
            {"id": "v1", "type": "vlan", "data": {"vlan_id": 40, "name": "SG", "svi_ip": "10.40.0.1/24"}},
            {"id": "i1", "type": "interface", "data": {"ports": "Gi1/0/4", "admin_state": "up", "mode": "access", "access_vlan": 40}},
            {"id": "l1", "type": "l2_safety", "data": {"ports": "Gi1/0/4", "portfast": True, "bpduguard": True}},
        ],
        "edges": [],
    }
    c = compile_graph_to_ir(graph)
    assert not c.errors
    cmds = render_ir_to_commands(c.ir, "handream_sg")
    assert "interface vlan 40" in cmds
    assert " spanning-tree portfast edge" in cmds
    assert " spanning-tree bpduguard enable" in cmds

    rb = render_ir_to_rollback_commands(c.ir, "handream_sg")
    assert "no vlan 40" in rb


def test_compile_and_render_new_domestic_switches_preview():
    graph = {
        "nodes": [
            {"id": "t1", "type": "target", "data": {"target_type": "devices", "device_ids": [1]}},
            {"id": "v1", "type": "vlan", "data": {"vlan_id": 50, "name": "DOMESTIC", "svi_ip": "10.50.0.1/24"}},
            {"id": "i1", "type": "interface", "data": {"ports": "Gi1/0/5", "admin_state": "up", "mode": "access", "access_vlan": 50}},
        ],
        "edges": [],
    }
    c = compile_graph_to_ir(graph)
    assert not c.errors
    for device_type in ("soltech_switch", "coreedge_switch", "nst_switch"):
        cmds = render_ir_to_commands(c.ir, device_type)
        assert "vlan 50" in cmds
        assert "interface Vlan50" in cmds
        rb = render_ir_to_rollback_commands(c.ir, device_type)
        assert "no vlan 50" in rb


def test_compile_requires_target():
    graph = {"nodes": [{"id": "v1", "type": "vlan", "data": {"vlan_id": 10, "name": "Users"}}], "edges": []}
    c = compile_graph_to_ir(graph)
    assert c.errors
