# app.py
import urllib.parse
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from typing import Dict
from datetime import datetime
import json
from models import SessionLocal, init_db, User, Message
from auth import get_password_hash, verify_password, create_access_token, decode_token

# Initialize database tables
init_db()

app = FastAPI()

# Allow React frontend (development mode)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# Database Dependency
# ----------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ----------------------------
# Connection Manager for Rooms
# ----------------------------
class ConnectionManager:
    def __init__(self):
        # room: {username: websocket}
        self.rooms: Dict[str, Dict[str, WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room: str, username: str):
        await websocket.accept()

        if room not in self.rooms:
            self.rooms[room] = {}

        self.rooms[room][username] = websocket

    def disconnect(self, websocket: WebSocket, room: str, username: str):
        if room in self.rooms and username in self.rooms[room]:
            del self.rooms[room][username]

            if not self.rooms[room]:
                del self.rooms[room]

    async def broadcast(self, room: str, message: str):
        if room in self.rooms:
            dead = []
            for username, ws in self.rooms[room].items():
                try:
                    await ws.send_text(message)
                except:
                    dead.append(username)

            # clean broken sockets
            for u in dead:
                del self.rooms[room][u]

    async def broadcast_user_list(self, room: str):
        """Send online user list to all clients in the room"""
        if room not in self.rooms:
            return

        users = list(self.rooms[room].keys())
        payload = {
            "type": "user_list",
            "users": users
        }

        for ws in self.rooms[room].values():
            await ws.send_json(payload)

manager = ConnectionManager()

# ----------------------------
# Save Message to PostgreSQL
# ----------------------------
def save_message(room: str, username: str, content: str):
    db = SessionLocal()
    msg = Message(
        room=room,
        username=username,
        content=content,
        timestamp=datetime.utcnow()
    )
    db.add(msg)
    db.commit()
    db.close()

# ----------------------------
# Signup Endpoint
# ----------------------------
@app.post("/signup")
def signup(data: dict, db=Depends(get_db)):
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        raise HTTPException(status_code=400, detail="username & password required")

    # check if user exists
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        raise HTTPException(status_code=400, detail="username already exists")

    hashed_pw = get_password_hash(password)
    user = User(username=username, hashed_password=hashed_pw)
    db.add(user)
    db.commit()

    # generate token
    token = create_access_token({"sub": username})
    return {"access_token": token, "token_type": "bearer"}

# ----------------------------
# Login Endpoint
# ----------------------------
@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db=Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    token = create_access_token({"sub": form_data.username})
    return {"access_token": token, "token_type": "bearer"}

# ----------------------------
# Fetch Chat History
# ----------------------------
@app.get("/messages/{room}")
def get_messages(room: str, limit: int = 50):
    db = SessionLocal()
    msgs = (
        db.query(Message)
        .filter(Message.room == room)
        .order_by(Message.timestamp.asc())
        .limit(limit)
        .all()
    )
    db.close()

    return [
        {
            "username": m.username,
            "content": m.content,
            "timestamp": m.timestamp.isoformat()
        }
        for m in msgs
    ]

# ----------------------------
# WebSocket Endpoint with JWT
# ----------------------------
@app.websocket("/ws/{room}/{username}")
async def websocket_endpoint(websocket: WebSocket, room: str, username: str):
    # extract token
    query = websocket.scope.get("query_string", b"").decode()
    params = dict(urllib.parse.parse_qsl(query))
    token = params.get("token")

    # validate token
    if not token or decode_token(token) != username:
        await websocket.close(code=1008)
        return

    # connect
    await manager.connect(websocket, room, username)
    await manager.broadcast(room, f"🟢 {username} joined room: {room}")
    await manager.broadcast_user_list(room)

    try:
        while True:
            message = await websocket.receive_text()

            # check if JSON typing event
            try:
                payload = json.loads(message)

                if payload.get("type") == "typing":
                # broadcast typing event to room
                    await manager.broadcast(room, json.dumps({
                        "type": "typing",
                        "username": username
                    }))
                    continue

                if payload.get("type") == "stop_typing":
                    # broadcast typing stop event
                    await manager.broadcast(room, json.dumps({
                        "type": "stop_typing",
                        "username": username
                    }))
                    continue

            except:
                pass  # not JSON → treat as chat message

                # Normal chat message
            save_message(room, username, message)
            await manager.broadcast(room, f"{username}: {message}")

    except WebSocketDisconnect:
        manager.disconnect(websocket, room, username)
        await manager.broadcast(room, f"🔴 {username} left room: {room}")
        await manager.broadcast_user_list(room)
