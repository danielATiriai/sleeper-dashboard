import { createHashRouter } from "react-router-dom";
import AppShell from "./layout/AppShell";
import Overview from "./pages/Overview";
import Team from "./pages/Team";
import PowerRankings from "./pages/PowerRankings";
import History from "./pages/History";
import Trades from "./pages/Trades";
import Draft from "./pages/Draft";
import Players from "./pages/Players";

export const router = createHashRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Overview /> },
      { path: "power", element: <PowerRankings /> },
      { path: "history", element: <History /> },
      { path: "trades", element: <Trades /> },
      { path: "draft", element: <Draft /> },
      { path: "players", element: <Players /> },
      { path: "team/:rid", element: <Team /> },
    ],
  },
]);
