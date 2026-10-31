from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job, LineageEdge, Mapping, Port, Transformation, Upload
from app.services.powercenter_parser import PowerCenterParseError, parse_powercenter_xml


async def parse_and_persist_upload(db: AsyncSession, upload_id: int, job_id: int) -> None:
    upload = await db.get(Upload, upload_id)
    job = await db.get(Job, job_id)
    if upload is None or job is None or job.upload_id != upload.id:
        raise ValueError("Upload or parse job no longer exists")
    job.status, job.progress, job.error = "running", 10, None
    upload.status = "parsing"
    await db.commit()
    try:
        parsed_mappings = parse_powercenter_xml(upload.raw_xml or "")
        job.progress = 35
        await db.flush()
        for parsed in parsed_mappings:
            mapping = Mapping(
                project_id=upload.project_id, upload_id=upload.id, name=parsed.name,
                description_ai=parsed.description, status="parsed",
            )
            db.add(mapping)
            await db.flush()
            port_lookup: dict[tuple[str, str], Port] = {}
            for order, parsed_transform in enumerate(parsed.transformations):
                transform = Transformation(
                    mapping_id=mapping.id, name=parsed_transform.name, type=parsed_transform.type,
                    logic_json={**parsed_transform.logic, "diagnostics": parsed.diagnostics}, seq_order=order,
                )
                db.add(transform)
                await db.flush()
                for parsed_port in parsed_transform.ports:
                    port = Port(
                        transformation_id=transform.id, name=parsed_port.name,
                        datatype=parsed_port.datatype, direction=parsed_port.direction,
                        expression=parsed_port.expression,
                    )
                    db.add(port)
                    await db.flush()
                    port_lookup[(parsed_transform.name, parsed_port.name)] = port
            unresolved = []
            for edge in parsed.edges:
                from_port = port_lookup.get((edge.from_instance, edge.from_field))
                to_port = port_lookup.get((edge.to_instance, edge.to_field))
                if from_port and to_port:
                    db.add(LineageEdge(mapping_id=mapping.id, from_port_id=from_port.id, to_port_id=to_port.id))
                else:
                    unresolved.append(
                        f"Unresolved connector: {edge.from_instance}.{edge.from_field} -> "
                        f"{edge.to_instance}.{edge.to_field}"
                    )
            if unresolved:
                raise PowerCenterParseError("; ".join(unresolved))
        upload.status, job.status, job.progress = "parsed", "completed", 100
        await db.commit()
    except Exception as exc:
        await db.rollback()
        upload = await db.get(Upload, upload_id)
        job = await db.get(Job, job_id)
        if upload and job:
            await db.execute(delete(Mapping).where(Mapping.upload_id == upload_id))
            upload.status, job.status, job.progress = "failed", "failed", 100
            job.error = str(exc)[:2000]
            await db.commit()
        raise
