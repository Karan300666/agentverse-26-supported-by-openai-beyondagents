import uuid

import logfire
from fastapi import APIRouter, HTTPException, Response, status

from app.core.security import CurrentPatient
from app.schemas.voice import VoiceSessionRead
from app.voice import realtime
from app.voice import session as voice_sessions

from app.db.session import DbSession
from app.schemas.voice import ToolCallRequest, ToolCallResult, VoiceSessionRead
from app.voice.tool_executor import execute_tool
from app.voice.tools import ToolContext

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/session", response_model=VoiceSessionRead, status_code=status.HTTP_201_CREATED)
async def start_session(patient: CurrentPatient):
    try:
        secret = await realtime.mint_client_secret()
    except realtime.RealtimeError:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, detail="Could not start the voice session"
        ) from None
    session_id = voice_sessions.create_session(patient.id)
    logfire.info("voice session started: session_id={id}", id=str(session_id))
    return VoiceSessionRead(session_id=session_id, client_secret=secret)


@router.delete("/session/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def end_session(session_id: uuid.UUID, patient: CurrentPatient):
    voice_session = voice_sessions.get_session(session_id)
    if voice_session is not None and voice_session.patient_id == patient.id:
        voice_sessions.end_session(session_id)
        logfire.info("voice session ended: session_id={id}", id=str(session_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post("/tool-call", response_model=ToolCallResult)
async def tool_call(data: ToolCallRequest, patient: CurrentPatient, db: DbSession):
    voice_session = voice_sessions.get_session(data.session_id)
    if voice_session is None or voice_session.patient_id != patient.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Voice session not found")

    ctx = ToolContext(db=db, patient=patient, session_id=data.session_id)
    return await execute_tool(ctx, data.tool_name, data.arguments)