import React, { useState, useEffect } from "react";

function App() {
  const [username, setUsername] = useState("");
  const [connected, setConnected] = useState(false);
  const [ws, setWs] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");

  const connect = () => {
    const socket = new WebSocket(`ws://localhost:8000/ws/${username}`);

    socket.onmessage = (event) => {
      setMessages((prev) => [...prev, event.data]);
    };

    setWs(socket);
    setConnected(true);
  };

  const sendMessage = () => {
    if (ws) {
      ws.send(input);
      setInput("");
    }
  };

  return (
    <div style={{ padding: 20 }}>
      {!connected ? (
        <div>
          <h2>Enter Your Name</h2>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <button onClick={connect}>Join Chat</button>
        </div>
      ) : (
        <div>
          <h2>Real-Time Chat</h2>

          <div
            style={{
              background: "#fff",
              height: 400,
              width: "80%",
              border: "1px solid #ccc",
              padding: 10,
              overflowY: "scroll",
            }}
          >
            {messages.map((msg, i) => (
              <p key={i}>{msg}</p>
            ))}
          </div>

          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type a message..."
          />
          <button onClick={sendMessage}>Send</button>
        </div>
      )}
    </div>
  );
}

export default App;
