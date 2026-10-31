"""Safe, namespace-tolerant PowerCenter repository XML parser."""
from dataclasses import dataclass, field
from defusedxml import ElementTree as DefusedET


SUPPORTED_TYPES = {
    "Expression", "Filter", "Joiner", "Lookup Procedure", "Lookup",
    "Aggregator", "Router", "Sorter", "Update Strategy",
}


class PowerCenterParseError(ValueError):
    pass


@dataclass
class ParsedPort:
    name: str
    datatype: str | None
    direction: str | None
    expression: str | None


@dataclass
class ParsedTransformation:
    name: str
    type: str
    ports: list[ParsedPort]
    logic: dict = field(default_factory=dict)


@dataclass
class ParsedEdge:
    from_instance: str
    from_field: str
    to_instance: str
    to_field: str


@dataclass
class ParsedMapping:
    name: str
    description: str | None
    transformations: list[ParsedTransformation]
    edges: list[ParsedEdge]
    diagnostics: list[str]


def _tag(element) -> str:
    return element.tag.rsplit("}", 1)[-1].upper()


def _children(element, name: str):
    expected = name.upper()
    return [child for child in element if _tag(child) == expected]


def _descendants(element, name: str):
    expected = name.upper()
    return [child for child in element.iter() if _tag(child) == expected]


def _direction(value: str | None) -> str | None:
    normalized = (value or "").strip().upper().replace(" ", "")
    return {"INPUT": "IN", "OUTPUT": "OUT", "INPUT/OUTPUT": "INOUT", "INPUTOUTPUT": "INOUT",
            "IN": "IN", "OUT": "OUT", "INOUT": "INOUT", "VARIABLE": "VAR", "VAR": "VAR"}.get(normalized)


def _field_port(field, default_direction: str) -> ParsedPort:
    return ParsedPort(
        name=field.attrib.get("NAME", "").strip(),
        datatype=(field.attrib.get("DATATYPE") or None),
        direction=_direction(field.attrib.get("PORTTYPE")) or default_direction,
        expression=(field.attrib.get("EXPRESSION") or None),
    )


def parse_powercenter_xml(xml: bytes | str) -> list[ParsedMapping]:
    try:
        root = DefusedET.fromstring(xml)
    except Exception as exc:
        raise PowerCenterParseError(f"Malformed or unsafe XML: {exc}") from exc
    if _tag(root) != "POWERMART":
        raise PowerCenterParseError("Expected a POWERMART root element")

    results: list[ParsedMapping] = []
    for mapping_node in _descendants(root, "MAPPING"):
        name = (mapping_node.attrib.get("NAME") or "").strip()
        if not name:
            raise PowerCenterParseError("A MAPPING is missing its NAME attribute")
        definitions: dict[str, ParsedTransformation] = {}
        diagnostics: list[str] = []

        for node, field_tag, kind, default_direction in (
            *[(n, "SOURCEFIELD", "Source Definition", "OUT") for n in _descendants(root, "SOURCE")],
            *[(n, "TARGETFIELD", "Target Definition", "IN") for n in _descendants(root, "TARGET")],
        ):
            node_name = (node.attrib.get("NAME") or "").strip()
            if node_name:
                definitions[node_name] = ParsedTransformation(
                    node_name, kind, [_field_port(f, default_direction) for f in _children(node, field_tag)]
                )

        for node in _children(mapping_node, "TRANSFORMATION"):
            transform_name = (node.attrib.get("NAME") or "").strip()
            transform_type = (node.attrib.get("TYPE") or "Unknown").strip()
            if not transform_name:
                raise PowerCenterParseError(f"Mapping {name} contains a transformation without NAME")
            if transform_type not in SUPPORTED_TYPES:
                diagnostics.append(f"Unsupported transformation type: {transform_type} ({transform_name})")
            table_attributes = {
                item.attrib.get("NAME", ""): item.attrib.get("VALUE", "")
                for item in _children(node, "TABLEATTRIBUTE") if item.attrib.get("NAME")
            }
            definitions[transform_name] = ParsedTransformation(
                transform_name,
                "Lookup" if transform_type == "Lookup Procedure" else transform_type,
                [_field_port(f, "INOUT") for f in _children(node, "TRANSFORMFIELD")],
                {"reusable": node.attrib.get("REUSABLE", "NO"), "table_attributes": table_attributes},
            )

        transformations: list[ParsedTransformation] = []
        instances = _children(mapping_node, "INSTANCE")
        if instances:
            for instance in instances:
                instance_name = (instance.attrib.get("NAME") or "").strip()
                reference = (instance.attrib.get("TRANSFORMATION_NAME") or instance.attrib.get("TRANSFORMATIONNAME") or "").strip()
                definition = definitions.get(reference)
                if not definition:
                    diagnostics.append(f"Unresolved instance reference: {instance_name} -> {reference}")
                    continue
                transformations.append(ParsedTransformation(
                    instance_name, definition.type, definition.ports, {**definition.logic, "definition_name": reference}
                ))
        else:
            transformations = list(definitions.values())

        edges = [ParsedEdge(
            connector.attrib.get("FROMINSTANCE", "").strip(),
            connector.attrib.get("FROMFIELD", "").strip(),
            connector.attrib.get("TOINSTANCE", "").strip(),
            connector.attrib.get("TOFIELD", "").strip(),
        ) for connector in _children(mapping_node, "CONNECTOR")]
        results.append(ParsedMapping(name, mapping_node.attrib.get("DESCRIPTION") or None, transformations, edges, diagnostics))
    if not results:
        raise PowerCenterParseError("No MAPPING elements were found")
    return results
