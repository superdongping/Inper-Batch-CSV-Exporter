"""Versioned interchange contract. Identity hints are never confirmations."""
import hashlib
import json
import re
from pathlib import Path


def identity(batch, session):
    parts = session.relative_to(batch).parts
    hits = [(i, re.findall(r'#[A-Za-z0-9_-]+', p)) for i, p in enumerate(parts)]
    hits = [(i, t) for i, t in hits if t]
    animal = hits[-1][1][0] if len(hits) == 1 and len(hits[0][1]) == 1 else ''
    sensor = '/'.join(parts[:hits[0][0]]) if animal else ''
    phase = re.search(r'\bNPR[ _-]+(E|R|Encoding|Retrieval)$', batch.name, re.I)
    label = ('Encoding' if phase[1].lower() in ('e', 'encoding') else 'Retrieval') if phase else batch.name
    return dict(animal_id=animal, sensor=sensor, condition=label,
                task='NPR' if phase else '', acquisition=parts[-1], identity_confirmed=False)


def write_dataset(output, records, jobs, version):
    rows = []
    for r, job in zip(records, jobs):
        # Stable across relocation/re-export; distinct paths distinguish repeated recordings.
        key = job.batch.name + '/' + job.session.relative_to(job.batch).as_posix() + ':' + r['source_db_sha256']
        rid = hashlib.sha256(key.encode('utf-8')).hexdigest()
        rows.append(dict(recording_id=rid, **identity(job.batch, job.session),
                         csv=Path(r['csv']).as_posix(), detailed_csv=Path(r['detailed_csv']).as_posix(),
                         metadata=Path(r['metadata']).as_posix(), video=Path(r['video']).as_posix(),
                         video_external=not r['video_copied'], csv_sha256=r['csv_sha256'],
                         detailed_csv_sha256=r['detailed_csv_sha256'], video_sha256=r['video_sha256']))
    ids = [r['recording_id'] for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate recording identity; use distinct batch names.')
    dataset = dict(schema_version=1, exporter_version=version, status='PASS',
                   dataset_id=hashlib.sha256('\n'.join(sorted(ids)).encode()).hexdigest(), recordings=rows)
    with (output / 'dataset.json').open('x', encoding='utf-8') as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)
