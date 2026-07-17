from enum import Enum, StrEnum, auto
from time import perf_counter
from typing import Any, Callable, List, Literal, Optional, Union
from uuid import UUID, uuid4

from PySide6.QtCore import (QObject, Signal)

import numpy as np

from suspension_designer.model_variables import ModelVariableElement
from suspension_designer.structures import EditorNode, NodeGroup, ReferencePlane


class SceneState(QObject):
    did_change = Signal()  # Signal to emit when the scene state changes

    def __init__(self, *, nodes: list[EditorNode] = [], edges: np.ndarray = np.array([]), groups: list[NodeGroup] = [], planes: list[ReferencePlane] = [], model_variables: list[ModelVariableElement] = [], is_editable: bool = True, name: str = "Unnamed Scene"):
        super().__init__()
        
        self._nodes = nodes
        for node in self._nodes:
            node.did_change.connect(self.did_change.emit)

        self.element_lookup = {}
    
        self._edges = edges
        self.is_editable = is_editable
        if planes is None:
            self.reference_planes: list[ReferencePlane] = []
        else:
            self.reference_planes = planes

        for plane in self.reference_planes:
            plane.did_change.connect(self.did_change.emit)


        self._groups = groups
        for group in self._groups:
            group.did_change.connect(self.did_change.emit)

        self._model_variables: list[ModelVariableElement] = model_variables
        for variable in self._model_variables:
            variable.did_change.connect(self.did_change.emit)

        self.name = name

        self.id = uuid4()  # Unique identifier for the scene
        

    def add_node(self, node: EditorNode):
        self._nodes.append(node)
        node.did_change.connect(self.did_change.emit)
        self.element_lookup |= {node.id: node}
        self.did_change.emit()  # Emit signal to notify that the scene has changed

    def add_reference_plane(self, plane: ReferencePlane):
        self.reference_planes.append(plane)
        plane.did_change.connect(self.did_change.emit)
        self.element_lookup |= {plane.id: plane}
        self.did_change.emit()  # Emit signal to notify that the scene has changed

    def add_group(self, group: NodeGroup):
        self._groups.append(group)
        group.did_change.connect(self.did_change.emit)
        self.element_lookup |= {group.id: group}
        self.did_change.emit()  # Emit signal to notify that the scene has changed

    def add_model_variable(self, variable: ModelVariableElement):
        self._model_variables.append(variable)
        variable.did_change.connect(self.did_change.emit)
        self.element_lookup |= {variable.id: variable}
        self.did_change.emit()  # Emit signal to notify that the scene has changed

    @property
    def nodes(self) -> list[EditorNode]:
        return self._nodes
    
    @nodes.setter
    def nodes(self, value):
        assert isinstance(value, list) and all(isinstance(node, EditorNode) for node in value), "Nodes must be a list of EditorNodes"
        
        for node in self._nodes:
            node.did_change.disconnect(self.did_change.emit)

        self._nodes = value
        self.element_lookup = {}
        for node in self._nodes:
            node.did_change.connect(self.did_change.emit)

        self.did_change.emit()  # Emit signal to notify that the scene has changed

    @property
    def edges(self) -> np.ndarray:
        return self._edges
    
    @edges.setter
    def edges(self, value):
        assert type(value) == np.ndarray and value.ndim == 2 and value.shape[1] == 2, "Edges must be a 2D numpy array with shape (N, 2)"
        
        self._edges = value
        self.did_change.emit()  # Emit signal to notify that the scene has changed

    @property
    def groups(self) -> list[NodeGroup]:
        return self._groups
    
    @groups.setter
    def groups(self, value):
        assert isinstance(value, list) and all(isinstance(group, NodeGroup) for group in value), "Groups must be a list of NodeGroups"
        
        for group in self._groups:
            group.did_change.disconnect(self.did_change.emit)

        self._groups = value
        self.element_lookup = {}
        for group in self._groups:
            group.did_change.connect(self.did_change.emit)

        self.did_change.emit()  # Emit signal to notify that the scene has changed

    @property
    def model_variables(self) -> list[ModelVariableElement]:
        return self._model_variables

    def delete_element(self, element):
        if type(element) == EditorNode:
            self.nodes.remove(element)
            element.did_change.disconnect(self.did_change.emit)
        elif type(element) == ReferencePlane:
            self.reference_planes.remove(element)
            element.did_change.disconnect(self.did_change.emit)
        elif type(element) == NodeGroup:
            self.groups.remove(element)
            element.did_change.disconnect(self.did_change.emit)
        elif isinstance(element, ModelVariableElement):
            self._model_variables.remove(element)
            element.did_change.disconnect(self.did_change.emit)
        else:
            raise ValueError("Element must be an EditorNode, ReferencePlane, or NodeGroup")
        
        self.did_change.emit()  # Emit signal to notify that the scene has changed

    def get_element_by_id(self, id: UUID, force_refresh: bool = False):
        if self.element_lookup is None or force_refresh:
            self.element_lookup = {node.id: node for node in self.nodes} | {plane.id: plane for plane in self.reference_planes} | {group.id: group for group in self.groups} | {variable.id: variable for variable in self._model_variables}

        return self.element_lookup.get(id, None)

    def to_dict(self):
        table = {
            'name': self.name,
            'nodes': [node.to_dict() for node in self.nodes],
            'edges': self.edges.tolist(),
            'planes': [plane.to_dict() for plane in self.reference_planes],
            'groups': [group.to_dict() for group in self.groups],
            'model_variables': [variable.to_dict() for variable in self.model_variables]
        }
    
        return table

    @staticmethod
    def from_dict(data: dict) -> 'SceneState':
        nodes = [EditorNode.from_dict(node_data) for node_data in data.get('nodes', [])]
        edges = np.array(data.get('edges', []), dtype=int)
        planes = [ReferencePlane.from_dict(plane_data) for plane_data in data.get('planes', [])]
        groups = [NodeGroup.from_dict(group_data) for group_data in data.get('groups', [])]
        variables = [ModelVariableElement.from_dict(variable_data) for variable_data in data.get("model_variables", [])]
        is_editable = data.get('is_editable', True)
        name = data.get('name', "Unnamed Scene")

        id_to_element = (
              {node.id: node for node in nodes}
            | {plane.id: plane for plane in planes}
            | {group.id: group for group in groups}
            | {variable.id: variable for variable in variables}
            )

        for node in nodes:
            node.fill_references(id_to_element)

        for group in groups:
            group.fill_references(id_to_element)

        for plane in planes:
            plane.fill_references(id_to_element)

        for element in variables:
            element.fill_references(id_to_element)

        return SceneState(
            nodes=nodes,
            edges=edges,
            planes=planes,
            groups=groups,
            model_variables=variables,
            is_editable=is_editable,
            name=name
        )
    
    def set(self, other: 'SceneState'):
        self.nodes = other.nodes
        self.edges = other.edges
        self.reference_planes = other.reference_planes
        self.groups = other.groups
        self.model_variables = other.model_variables
        self.is_editable = other.is_editable

        self.did_change.emit()  # Emit signal to notify that the scene has changed

    def copy(self) -> 'SceneState':
        return SceneState.from_dict(self.to_dict())