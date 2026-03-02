# 简历模块真实业务测试

本目录测试目标：
- 不使用 mock；
- 直接打真实 API；
- 使用真实测试数据 `tests/data/resume.pdf`；
- 使用真实数据库（独立测试库 `tests/data/resume_module_test.db`）。

## 用例清单

- `test_upload_resume.py`: `POST /api/resumes/upload`
- `test_list_resumes.py`: `GET /api/resumes`
- `test_get_resume_detail.py`: `GET /api/resumes/<resume_id>`
- `test_update_resume.py`: `PUT /api/resumes/<resume_id>`
- `test_delete_resume.py`: `DELETE /api/resumes/<resume_id>`
- `test_retry_parse_resume.py`: `POST /api/resumes/<resume_id>/retry-parse`
- `test_get_resume_by_room.py`: `GET /api/resume/<room_id>`

## 运行方式

```bash
python -m unittest discover -s tests/modules/resume -p 'test_*.py' -v
```
