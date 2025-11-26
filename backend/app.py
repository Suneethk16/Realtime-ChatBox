# app.py
import urllib.parse
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import Dict

from models import SessionLocal, init_db, User
from auth import get_password_hash, verify_password, create_access_token, decode_token

# Initialize DB (creates file and tables if not exist)
init_db()

app = FastAPI()

# Allow React frontend (dev). Replace with your domain in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple in-module ConnectionManager with rooms
class ConnectionManager:
    def __init__(self):
        self.rooms: Dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room: str):
        await websocket.accept()
        if room not in self.rooms:
            self.rooms[room] = []
        self.rooms[room].append(websocket)

    def disconnect(self, websocket: WebSocket, room: str):
        if room in self.rooms and websocket in self.rooms[room]:
            self.rooms[room].remove(websocket)
            if not self.rooms[room]:
                del self.rooms[room]

    async def broadcast(self, room: str, message: str):
        if room in self.rooms:
            for connection in list(self.rooms[room]):
                try:
                    await connection.send_text(message)
                except Exception:
                    # remove dead connection
                    self.disconnect(connection, room)

manager = ConnectionManager()

# Pydantic models
class SignupIn(BaseModel):
    username: str
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

# Dependency: get DB session (simple)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Signup endpoint
@app.post("/signup", response_model=TokenOut)
def signup(data: SignupIn, db=Depends(get_db)):
    username = data.username.strip()
    raw_password = data.password
    if not username or not raw_password:
        raise HTTPException(status_code=400, detail="username and password required")
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        raise HTTPException(status_code=400, detail="username already registered")
    hashed = get_password_hash(raw_password)
    user = User(username=username, hashed_password=hashed)
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": username})
    return {"access_token": token}

# Login endpoint (OAuth2PasswordRequestForm compatible)
@app.post("/login", response_model=TokenOut)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db=Depends(get_db)):
    username = form_data.username
    password = form_data.password
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token = create_access_token({"sub": username})
    return {"access_token": token}

# Helper to get current username from token (for HTTP routes)
def get_current_username_from_token(token: str = Depends(lambda: None)):
    # not used as a FastAPI dependency in this example; you can implement OAuth2PasswordBearer if needed
    pass

# WebSocket endpoint with token in query string
@app.websocket("/ws/{room}/{username}")
async def websocket_endpoint(websocket: WebSocket, room: str, username: str):
    """
    Expect: ws://host/ws/{room}/{username}?token=JWT_HERE
    Token is validated before accepting messages and broadcasting.
    """
    # Extract token from query params
    query = websocket.scope.get("query_string", b"").decode()
    params = dict(urllib.parse.parse_qsl(query))
    token = params.get("token")
    if not token:
        # cannot accept without token — close connection
        await websocket.close(code=1008)  # policy violation
        return

    # decode and validate
    token_username = decode_token(token)
    if not token_username or token_username != username:
        # token invalid or username mismatch
        await websocket.close(code=1008)
        return

    # Passed checks — connect
    await manager.connect(websocket, room)
    await manager.broadcast(room, f"🟢 {username} joined room: {room}")

    try:
        while True:
            data = await websocket.receive_text()
            # optionally verify token again per-message if you want
            await manager.broadcast(room, f"{username}: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket, room)
        await manager.broadcast(room, f"🔴 {username} left room: {room}")
