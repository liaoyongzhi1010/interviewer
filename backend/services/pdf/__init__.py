"""
报告文档生成服务
提供报告文档生成功能的统一入口
"""

from backend.services.pdf.pdf_generator import PDFReportGenerator

# 全局报告文档生成器实例
_pdf_generator = None


def get_pdf_generator() -> PDFReportGenerator:
    """
    获取报告文档生成器实例（单例模式）

    返回：
        报告文档生成器实例
    """
    global _pdf_generator
    if _pdf_generator is None:
        _pdf_generator = PDFReportGenerator()
    return _pdf_generator


__all__ = ['get_pdf_generator', 'PDFReportGenerator']
