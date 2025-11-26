import React, { useState, useEffect } from "react";

const API_BASE = "http://localhost:8000";

function App() {
  const [username, setUsername] = useState("");
  const [room, setRoom] = useState("");
  const [connected, setConnected] = useState(false);
  const [ws, setWs] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");

  const [token, setToken] = useState(localStorage.getItem("token") || "");
  const [authUser, setAuthUser] = useState(localStorage.getItem("username") || "");

  // LOGIN
  async function login(e) {
    e.preventDefault();
    const form = new FormData();
    form.append("username", username);
    form.append("password", prompt("Enter password for login (demo):")); // simple demo; replace with proper input
    const resp = await fetch(`${API_BASE}/login`, {
      method: "POST",
      body: form
    });
    if (!resp.ok) {
      alert("Login failed");
      return;
    }
    const data = await resp.json();
    localStorage.setItem("token", data.access_token);
    localStorage.setItem("username", username);
    setToken(data.access_token);
    setAuthUser(username);
    alert("Logged in!");
  }

  // SIGNUP (demo)
  async function signup() {
    const pw = prompt("Choose a password (demo):");
    const resp = await fetch(`${API_BASE}/signup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password: pw })
    });
    if (!resp.ok) {
      const j = await resp.json();
      alert("Signup failed: " + (j.detail || JSON.stringify(j)));
      return;
    }
    const j = await resp.json();
    localStorage.setItem("token", j.access_token);
    localStorage.setItem("username", username);
    setToken(j.access_token);
    setAuthUser(username);
    alert("Signed up & logged in!");
  }

  // Connect WebSocket with token in query string
  function connect() {
    if (!authUser || !room) {
      alert("set username (login/signup) and room");
      return;
    }
    const t = encodeURIComponent(token);
    const socket = new WebSocket(`ws://localhost:8000/ws/${room}/${authUser}?token=${t}`);

    socket.onmessage = (event) => {
      setMessages(prev => [...prev, event.data]);
    };

    socket.onopen = () => {
      setConnected(true);
      setWs(socket);
    };

    socket.onclose = () => {
      setConnected(false);
      setWs(null);
    };

    socket.onerror = (err) => {
      console.error("Socket error", err);
      alert("WebSocket error. See console.");
    };
  }

  function sendMessage() {
    if (ws && input.trim()) {
      ws.send(input);
      setInput("");
    }
  }

  function logout() {
    localStorage.removeItem("token");
    localStorage.removeItem("username");
    setToken("");
    setAuthUser("");
  }

  return (
    <div style={{ padding: 20 }}>
      <h2>Auth + Rooms Chat (Demo)</h2>

      {!authUser ? (
        <div>
          <input placeholder="username" value={username} onChange={e => setUsername(e.target.value)} />
          <button onClick={signup}>Signup</button>
          <button onClick={login}>Login</button>
        </div>
      ) : (
        <div>
          <p>Logged in as <b>{authUser}</b> <button onClick={logout}>Logout</button></p>
          {!connected ? (
            <>
              <input placeholder="room" value={room} onChange={e => setRoom(e.target.value)} />
              <button onClick={connect}>Join Room</button>
            </>
          ) : (
            <>
              <p>Room: {room}</p>
              <div style={{ background: "#fff", height: 300, width: "80%", border: "1px solid #ccc", padding: 10, overflowY: "scroll" }}>
                {messages.map((m, i) => <p key={i}>{m}</p>)}
              </div>
              <input value={input} onChange={e => setInput(e.target.value)} placeholder="Type a message" />
              <button onClick={sendMessage}>Send</button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default App;
