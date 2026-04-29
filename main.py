from fastapi import FastAPI, Depends, HTTPException

from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime

from sqlalchemy.orm import sessionmaker, declarative_base, Session

from pydantic import BaseModel, ConfigDict

from datetime import datetime

import uvicorn

from typing import Optional

# ==========================================

# 1. DATENBANK SETUP

# ==========================================

SQLALCHEMY_DATABASE_URL = "sqlite:///./termine.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class TerminDB(Base):
    __tablename__ = "termine"

    id = Column(Integer, primary_key=True, index=True)

    titel = Column(String, index=True)

    ort = Column(String)

    genaue_lage = Column(String, nullable=True)

    art_der_massnahme = Column(String)

    startdatum = Column(String, nullable=True)

    enddatum = Column(String, nullable=True)

    ausfuehrende_stelle = Column(String, nullable=True)

    link = Column(String, index=True)

    ist_neu = Column(Boolean, default=True)

    gefunden_am = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)


# ==========================================

# 2. PYDANTIC MODELLE (API Validierung)

# ==========================================

class TerminCreate(BaseModel):
    titel: str

    ort: str

    genaue_lage: Optional[str] = None

    art_der_massnahme: str

    startdatum: Optional[str] = None

    enddatum: Optional[str] = None

    ausfuehrende_stelle: Optional[str] = None

    link: str


class TerminResponse(BaseModel):
    id: int

    titel: str

    ort: str

    genaue_lage: Optional[str] = None

    art_der_massnahme: str

    startdatum: Optional[str] = None

    enddatum: Optional[str] = None

    ausfuehrende_stelle: Optional[str] = None

    link: str

    ist_neu: bool

    gefunden_am: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================

# 3. FASTAPI SCHNITTSTELLE

# ==========================================

app = FastAPI(title="Tiefbau Crawler API", description="Schnittstelle für Telekommunikations-Synergien")


def get_db():
    db = SessionLocal()

    try:

        yield db

    finally:

        db.close()


@app.post("/termine/", response_model=TerminResponse)
def create_termin(termin: TerminCreate, db: Session = Depends(get_db)):
    # NEU: Wir prüfen jetzt, ob der TITEL schon in der Datenbank steht!

    db_termin = db.query(TerminDB).filter(TerminDB.titel == termin.titel).first()

    if db_termin:
        raise HTTPException(status_code=400, detail="Baumaßnahme (Titel) existiert bereits")

    neuer_termin = TerminDB(

        titel=termin.titel,

        ort=termin.ort,

        genaue_lage=termin.genaue_lage,

        art_der_massnahme=termin.art_der_massnahme,

        startdatum=termin.startdatum,

        enddatum=termin.enddatum,

        ausfuehrende_stelle=termin.ausfuehrende_stelle,

        link=termin.link

    )

    db.add(neuer_termin)

    db.commit()

    db.refresh(neuer_termin)

    return neuer_termin


@app.get("/termine/", response_model=list[TerminResponse])
def get_alle_termine(db: Session = Depends(get_db)):
    return db.query(TerminDB).all()


@app.get("/termine/neue", response_model=list[TerminResponse])
def get_neue_termine(db: Session = Depends(get_db)):
    return db.query(TerminDB).filter(TerminDB.ist_neu == True).all()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)