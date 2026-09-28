import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { PageLoader } from './components/ui'
import { useAuth } from './lib/auth'
import Assistant from './pages/Assistant'
import Compare from './pages/Compare'
import DecisionPack from './pages/DecisionPack'
import Explore from './pages/Explore'
import Login from './pages/Login'
import ManagerHome from './pages/ManagerHome'
import MissionDetail from './pages/MissionDetail'
import Missions from './pages/Missions'
import MyProperties from './pages/MyProperties'
import NewProperty from './pages/NewProperty'
import Pipeline from './pages/Pipeline'
import PropertyDetail from './pages/PropertyDetail'
import ReportDetail from './pages/ReportDetail'
import Reports from './pages/Reports'
import Assignments from './pages/Assignments'
import Studies from './pages/Studies'
import StudyDetail from './pages/StudyDetail'
import SurveyUnit from './pages/SurveyUnit'
import Team from './pages/Team'

function Home() {
  const { user } = useAuth()
  switch (user?.role) {
    case 'bd_manager':
      return <ManagerHome />
    case 'bd_exec':
      return <Missions />
    case 'survey_manager':
      return <Studies />
    default:
      return <Assignments />
  }
}

export default function App() {
  const { user, loading } = useAuth()
  if (loading) return <PageLoader label="Starting SiteScout…" />
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      {!user ? (
        <Route path="*" element={<Navigate to="/login" replace />} />
      ) : (
        <>
          <Route path="/properties/:id/pack" element={<DecisionPack />} />
          <Route element={<Layout />}>
            <Route path="/" element={<Home />} />
            <Route path="/explore" element={<Explore />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/reports/:id" element={<ReportDetail />} />
            <Route path="/compare" element={<Compare />} />
            <Route path="/pipeline" element={<Pipeline />} />
            <Route path="/missions" element={<Missions />} />
            <Route path="/missions/:id" element={<MissionDetail />} />
            <Route path="/properties/new" element={<NewProperty />} />
            <Route path="/properties/:id" element={<PropertyDetail />} />
            <Route path="/my-properties" element={<MyProperties />} />
            <Route path="/studies" element={<Studies />} />
            <Route path="/studies/:id" element={<StudyDetail />} />
            <Route path="/team" element={<Team />} />
            <Route path="/survey/:id" element={<SurveyUnit />} />
            <Route path="/assistant" element={<Assistant />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </>
      )}
    </Routes>
  )
}
