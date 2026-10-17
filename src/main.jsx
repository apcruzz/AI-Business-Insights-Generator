// Browser entry point: mount App into index.html; App starts the dashboard controller.
import { createRoot } from "react-dom/client";
import App from "./App.jsx";

createRoot(document.getElementById("root")).render(<App />);
