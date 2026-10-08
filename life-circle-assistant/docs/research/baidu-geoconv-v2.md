# 百度地图 Geoconv V2 坐标转换契约

核对日期：2026-10-08。

## 项目采用的接口

- 请求：`GET https://api.map.baidu.com/geoconv/v2/`
- `coords`：`经度,纬度`，多个坐标用 `;` 分隔；Web API 单次最多 100 点。
- `model=1`：GCJ-02（高德/腾讯）→ BD-09 经纬度。
- `model=2`：WGS84/GPS → BD-09 经纬度。
- `ak`：百度地图 Web 服务 AK；项目公共请求层统一附加。
- 成功结果：`{"status": 0, "result": [{"x": 经度, "y": 纬度}]}`。

项目内部、空间分析、缓存及报告统一使用 BD-09。BD-09 输入不消耗 API；WGS84/GCJ-02 输入通过 Geoconv V2 转换后再做黄埔区范围校验和逆地理编码。

## 可靠性约束

- 按 100 点上限分块，并保持输入顺序合并结果。
- 不能只看 HTTP 状态码；必须检查 JSON `status == 0`。鉴权失败也可能返回 HTTP 200 和非零业务状态。
- 每块必须校验返回数量与输入数量一致。
- 每项必须包含 `x/y`，且值必须可解析为有限浮点数。
- `status=1`（内部错误）、网络超时、HTTP 限流或服务端错误可有限重试；参数、坐标格式和 AK 错误不应盲目重试。
- 离线快照只允许 BD-09 原样通过，不伪造 WGS84/GCJ-02 转换结果。

## 官方来源

- [坐标转换服务基础接口](https://lbsyun.baidu.com/docs/webapi?title=geoconv/guide/changeposition-base)
- [坐标转换服务概览](https://lbsyun.baidu.com/docs/webapi?title=geoconv/guide/changeposition)
- [使用准备与 AK](https://lbsyun.baidu.com/docs/webapi?title=geoconv/guide/changeposition/prepare)
- [坐标转换更新日志](https://lbsyun.baidu.com/docs/webapi?title=geoconv/guide/changeposition-update)
- [百度 WebAPI 示例中心](https://lbsyun.baidu.com/webapi/demo-center?serviceid=18)

旧 `/geoconv/v1/` 的 `from/to` 参数不作为新实现依据；当前官方文档使用 V2 `model` 契约。

## 本地验证记录

2026-10-08 使用本地已配置的真实百度 Web 服务 AK，对 `model=1`（GCJ-02 → BD-09）和 `model=2`（WGS84 → BD-09）各执行一次受控契约验证，均成功返回数量一致、字段完整且位于广州范围内的有限坐标。验证输出仅记录成功状态，未打印 AK、输入坐标、返回坐标或响应正文。
