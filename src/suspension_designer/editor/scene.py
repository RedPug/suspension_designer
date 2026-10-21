from enum import Enum, StrEnum, auto
from time import perf_counter
from typing import Any, Callable, List, Literal, Optional, Union
from uuid import UUID, uuid4

from PySide6.QtCore import (QObject, Signal)

import numpy as np

from suspension_designer.elements.geometry_builder import GeometryBuilder
from suspension_designer.elements.geometry import ReferenceGeometryElement
from suspension_designer.solver.model_variables import ModelVariableElement
from suspension_designer.elements.nodes import EditorNode, NodeGroup


class SceneState(QObject):
    did_change = Signal()  # Signal to emit when the scene state changes

    def __init__(self, *, nodes: list[EditorNode] = [], edges: np.ndarray = np.array([]), groups: list[NodeGroup] = [], reference_geometry: list[ReferenceGeometryElement] = [], model_variables: list[ModelVariableElement] = [], is_editable: bool = True, name: str = "Unnamed Scene"):
        super().__init__()
        
        self._nodes = nodes
        for node in self._nodes:
            node.did_change.connect(self.did_change.emit)

        self._element_lookup = None
    
        self._edges = edges
        self.is_editable = is_editable
        if reference_geometry is None:
            self._reference_geometry: list[ReferenceGeometryElement] = []
        else:
            self._reference_geometry = reference_geometry

        for element in self._reference_geometry:
            element.did_change.connect(self.did_change.emit)


        self._groups = groups
        for group in self._groups:
            group.did_change.connect(self.did_change.emit)

        self._model_variables: list[ModelVariableElement] = model_variables
        for variable in self._model_variables:
            variable.did_change.connect(self.did_change.emit)

        self.name = name

        self.id = uuid4()  # Unique identifier for the scene

    def add_element(self, element):
        if isinstance(element, EditorNode):
            self.add_node(element)
        elif isinstance(element, ReferenceGeometryElement):
            self.add_reference_geometry(element)
        elif isinstance(element, NodeGroup):
            self.add_group(element)
        elif isinstance(element, ModelVariableElement):
            self.add_model_variable(element)
        else:
            raise ValueError("Element must be an EditorNode, ReferenceGeometryElement, NodeGroup, or ModelVariableElement")

    def add_node(self, node: EditorNode):
        self._nodes.append(node)
        node.did_change.connect(self.did_change.emit)
        self._element_lookup |= {node.id: node}
        self.did_change.emit()  # Emit signal to notify that the scene has changed

    def add_reference_geometry(self, element: ReferenceGeometryElement):
        self._reference_geometry.append(element)
        element.did_change.connect(self.did_change.emit)
        self._element_lookup |= {element.id: element}
        self.did_change.emit()  # Emit signal to notify that the scene has changed

    def add_group(self, group: NodeGroup):
        self._groups.append(group)
        group.did_change.connect(self.did_change.emit)
        self._element_lookup |= {group.id: group}
        self.did_change.emit()  # Emit signal to notify that the scene has changed

    def add_model_variable(self, variable: ModelVariableElement):
        self._model_variables.append(variable)
        variable.did_change.connect(self.did_change.emit)
        self._element_lookup |= {variable.id: variable}
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
        self._element_lookup = None
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
        self._element_lookup = None
        for group in self._groups:
            group.did_change.connect(self.did_change.emit)

        self.did_change.emit()  # Emit signal to notify that the scene has changed

    @property
    def reference_geometry(self) -> list[ReferenceGeometryElement]:
        return self._reference_geometry

    @reference_geometry.setter
    def reference_geometry(self, value):
        assert isinstance(value, list) and all(isinstance(element, ReferenceGeometryElement) for element in value), "Reference geometry must be a list of ReferenceGeometryElements"
        
        for element in self._reference_geometry:
            element.did_change.disconnect(self.did_change.emit)

        self._reference_geometry = value
        self._element_lookup = None
        for element in self._reference_geometry:
            element.did_change.connect(self.did_change.emit)

        self.did_change.emit()  # Emit signal to notify that the scene has changed

    @property
    def model_variables(self) -> list[ModelVariableElement]:
        return self._model_variables

    @model_variables.setter
    def model_variables(self, value):
        assert isinstance(value, list) and all(isinstance(variable, ModelVariableElement) for variable in value), "Model variables must be a list of ModelVariableElements"
        
        for variable in self._model_variables:
            variable.did_change.disconnect(self.did_change.emit)

        self._model_variables = value
        self._element_lookup = None
        for variable in self._model_variables:
            variable.did_change.connect(self.did_change.emit)

        self.did_change.emit()  # Emit signal to notify that the scene has changed

    def delete_element(self, element):
        if type(element) == EditorNode:
            self.nodes.remove(element)
            element.did_change.disconnect(self.did_change.emit)
        elif isinstance(element, ReferenceGeometryElement):
            self._reference_geometry.remove(element)
            element.did_change.disconnect(self.did_change.emit)
        elif type(element) == NodeGroup:
            self.groups.remove(element)
            element.did_change.disconnect(self.did_change.emit)
        elif isinstance(element, ModelVariableElement):
            self._model_variables.remove(element)
            element.did_change.disconnect(self.did_change.emit)
        else:
            raise ValueError("Element must be an EditorNode, ReferencePlane, or NodeGroup")

        self._element_lookup.pop(element.id, None)
        
        self.did_change.emit()  # Emit signal to notify that the scene has changed

    def get_element_by_id(self, id: UUID, force_refresh: bool = False):
        if self._element_lookup is None or force_refresh:
            self._element_lookup = {node.id: node for node in self.nodes} | {element.id: element for element in self._reference_geometry} | {group.id: group for group in self.groups} | {variable.id: variable for variable in self._model_variables}

        return self._element_lookup.get(id, None)
    
    def update_node_positions(self, node_positions: np.ndarray):
        for i, node in enumerate(self.nodes):
            if 0 <= i < len(node_positions):
                node.world_position = node_positions[i]
        # print("Updated node positions")

    def strip_reference(self) -> 'SceneState':
        # Create a new instance without any reference geometry
        scene = SceneState.from_dict(self.to_dict())
        scene._reference_geometry = []
        return scene

    def to_dict(self):
        return {
            'name': self.name,
            'nodes': [node.to_dict() for node in self.nodes],
            'edges': self.edges.tolist(),
            'geometry': [element.to_dict() for element in self._reference_geometry],
            'groups': [group.to_dict() for group in self.groups],
            'model_variables': [variable.to_dict() for variable in self.model_variables]
        }

    @staticmethod
    def from_dict(data: dict) -> 'SceneState':
        nodes = [EditorNode.from_dict(node_data) for node_data in data.get('nodes', [])]
        edges = np.array(data.get('edges', []), dtype=int)
        geometry = [ReferenceGeometryElement.from_dict(geom_data) for geom_data in data.get('geometry', [])]
        groups = [NodeGroup.from_dict(group_data) for group_data in data.get('groups', [])]
        variables = [ModelVariableElement.from_dict(variable_data) for variable_data in data.get("model_variables", [])]
        is_editable = data.get('is_editable', True)
        name = data.get('name', "Unnamed Scene")

        id_to_element = (
              {node.id: node for node in nodes}
            | {element.id: element for element in geometry}
            | {group.id: group for group in groups}
            | {variable.id: variable for variable in variables}
            )

        print()
        print("Geometry Elements:")
        for element in geometry:
            print(f"  - {element.id}: {element.__class__.__name__} with constraints: {[str(c) for c in element._constraints]}")

        print()

        for node in nodes:
            node.fill_references(id_to_element)

        for group in groups:
            group.fill_references(id_to_element)

        for element in geometry:
            element.fill_references(id_to_element)

        for element in variables:
            element.fill_references(id_to_element)

        GeometryBuilder(geometry).rebuild_all_geometry()

        return SceneState(
            nodes=nodes,
            edges=edges,
            reference_geometry=geometry,
            groups=groups,
            model_variables=variables,
            is_editable=is_editable,
            name=name
        )
    
    def restore(self, other: 'SceneState'):
        self.nodes = other.nodes
        self.edges = other.edges
        self._reference_geometry = other._reference_geometry
        self.groups = other.groups
        self.model_variables = other.model_variables
        self.is_editable = other.is_editable

        self._element_lookup = None

        self.did_change.emit()  # Emit signal to notify that the scene has changed

    def copy(self) -> 'SceneState':
        return SceneState.from_dict(self.to_dict())