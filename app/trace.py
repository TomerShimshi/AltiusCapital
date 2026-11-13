from sqlalchemy import func, insert, select, update

from app.models import trace_runs, trace_steps


class Tracer:
    def __init__(self, engine):
        self.engine = engine

    def start_run(self, question: str) -> int:
        with self.engine.begin() as c:
            return c.execute(insert(trace_runs).values(question=question)).inserted_primary_key[0]

    def step(self, run_id, kind, name, payload, model=None, ms=0) -> None:
        with self.engine.begin() as c:
            seq = c.execute(select(func.count()).select_from(trace_steps)
                            .where(trace_steps.c.run_id == run_id)).scalar() + 1
            c.execute(insert(trace_steps).values(run_id=run_id, seq=seq, kind=kind, name=name,
                                                 model=model, payload=payload, ms=ms))

    def finish_run(self, run_id, answer, citations) -> None:
        with self.engine.begin() as c:
            c.execute(update(trace_runs).where(trace_runs.c.id == run_id)
                      .values(answer=answer, citations=citations, finished=func.now()))

    def get_run(self, run_id) -> dict:
        with self.engine.connect() as c:
            r = c.execute(select(trace_runs).where(trace_runs.c.id == run_id)).mappings().one()
            steps = c.execute(select(trace_steps).where(trace_steps.c.run_id == run_id)
                              .order_by(trace_steps.c.seq)).mappings().all()
        return {"id": r["id"], "question": r["question"], "answer": r["answer"],
                "citations": r["citations"], "steps": [dict(s) for s in steps]}
