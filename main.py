from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from pydantic import BaseModel
from datetime import datetime
import uvicorn

# ==========================================
# 1. DATENBANK SETUP (SQLite + SQLAlchemy)
# ==========================================
SQLALCHEMY_DATABASE_URL = "sqlite:///./termine.db"
# check_same_thread=False wird für SQLite in FastAPI benötigt
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# Das Datenbank-Modell (Wie die Tabelle aussieht)
class TerminDB(Base):
    __tablename__ = "termine"

    id = Column(Integer, primary_key=True, index=True)
    titel = Column(String, index=True)
    datum = Column(String)
    link = Column(String, unique=True, index=True)  # Der Link ist unique, so erkennen wir Duplikate
    ist_neu = Column(Boolean, default=True)
    gefunden_am = Column(DateTime, default=datetime.utcnow)


# Erstelle die Tabellen in der Datenbank-Datei
Base.metadata.create_all(bind=engine)


# ==========================================
# 2. PYDANTIC MODELLE (Für die API Validierung)
# ==========================================
class TerminCreate(BaseModel):
    titel: str
    datum: str
    link: str


class TerminResponse(BaseModel):
    id: int
    titel: str
    datum: str
    link: str
    ist_neu: bool
    gefunden_am: datetime

    class Config:
        from_attributes = True


# ==========================================
# 3. FASTAPI SCHNITTSTELLE (Die API)
# ==========================================
app = FastAPI(title="Termin Crawler API", description="Schnittstelle für den Termin-Webcrawler")


# Hilfsfunktion, um eine Datenbank-Session zu bekommen
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.post("/termine/", response_model=TerminResponse)
def create_termin(termin: TerminCreate, db: Session = Depends(get_db)):
    """
    Diese Route wird später vom Crawler aufgerufen, um einen neuen Termin zu speichern.
    """
    # Prüfen, ob der Link schon existiert (Gedächtnis-Funktion!)
    db_termin = db.query(TerminDB).filter(TerminDB.link == termin.link).first()
    if db_termin:
        raise HTTPException(status_code=400, detail="Termin (Link) existiert bereits")

    # Neuen Termin anlegen
    neuer_termin = TerminDB(titel=termin.titel, datum=termin.datum, link=termin.link)
    db.add(neuer_termin)
    db.commit()
    db.refresh(neuer_termin)
    return neuer_termin


@app.get("/termine/", response_model=list[TerminResponse])
def get_alle_termine(db: Session = Depends(get_db)):
    """Holt alle Termine aus der Datenbank."""
    return db.query(TerminDB).all()


@app.get("/termine/neue", response_model=list[TerminResponse])
def get_neue_termine(db: Session = Depends(get_db)):
    """Holt nur die Termine, die noch als 'neu' markiert sind."""
    return db.query(TerminDB).filter(TerminDB.ist_neu == True).all()


@app.put("/termine/{termin_id}/gelesen")
def markiere_als_gelesen(termin_id: int, db: Session = Depends(get_db)):
    """Markiert einen Termin als gelesen (ist_neu = False)."""
    db_termin = db.query(TerminDB).filter(TerminDB.id == termin_id).first()
    if not db_termin:
        raise HTTPException(status_code=404, detail="Termin nicht gefunden")

    db_termin.ist_neu = False
    db.commit()
    return {"message": "Termin wurde als gelesen markiert."}


# ==========================================
# 4. SERVER START (Zum lokalen Testen)
# ==========================================
if __name__ == "__main__":
    # Startet den API-Server auf Port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)