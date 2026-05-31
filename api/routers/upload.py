"""
文件上传路由
POST /upload/resume  -> 解析 PDF/Word/TXT，返回文本内容
"""
from __future__ import annotations

import io

from fastapi import APIRouter, File, HTTPException, UploadFile
from loguru import logger

from api.schemas import UploadResponse

router = APIRouter(prefix="/upload", tags=["文件上传"])


@router.post("/resume", response_model=UploadResponse)
async def upload_resume(file: UploadFile = File(...)):
    """
    上传简历文件（PDF / DOCX / TXT），返回提取的纯文本
    """
    filename = file.filename or ""
    content  = await file.read()
    text     = ""

    try:
        if filename.endswith(".pdf"):
            text = _extract_pdf(content)
        elif filename.endswith((".docx", ".doc")):
            text = _extract_docx(content)
        elif filename.endswith((".txt", ".md")):
            text = content.decode("utf-8", errors="ignore")
        else:
            raise HTTPException(
                status_code=400,
                detail="不支持的文件格式，请上传 PDF / DOCX / TXT",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("简历解析失败: {}", e)
        raise HTTPException(status_code=500, detail=f"文件解析失败: {e}")

    if not text.strip():
        raise HTTPException(status_code=422, detail="文件内容为空，无法解析")

    logger.info("简历上传成功: {} {} 字符", filename, len(text))
    return UploadResponse(
        filename=filename,
        text=text,
        char_count=len(text),
    )


def _extract_pdf(content: bytes) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(
            page.extract_text() or "" for page in reader.pages
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="pypdf 未安装，无法解析 PDF")


def _extract_docx(content: bytes) -> str:
    try:
        import docx
        doc = docx.Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs)
    except ImportError:
        raise HTTPException(status_code=500, detail="python-docx 未安装，无法解析 DOCX")