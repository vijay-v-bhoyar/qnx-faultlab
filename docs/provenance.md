# Provenance and validation
FaultLab source, test fixtures and report design were authored for this project with Codex assistance in November 2026. No upstream repository history, QNX SDK headers/libraries/binaries, system images or credentials are included.

API semantics were checked against primary QNX 8.0 documentation:
- [Message-passing architecture](https://www.qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.sys_arch/topic/ipc_Message_API.html)
- [MsgSend](https://www.qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.lib_ref/topic/m/msgsend.html)
- [TimerTimeout](https://www.qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.lib_ref/topic/t/timertimeout.html)
- [QNX QEMU setup](https://www.qnx.com/developers/docs/qnxeverywhere/com.qnx.doc.target_images/topic/qsti_qemu/about.html)

Documentation/API review alone does not prove compilation or native behavior. On November 3, 2026, the unchanged runner source from commit f130727e7a299e9ea2b030cdb9712706b10c61db was compiled with licensed SDP 8.0 and exercised on a disposable QNX 8.0.0 x86_64/QEMU target. The retained sample is actual local output; see [native validation](native-validation.md). Synthetic Python/browser checks remain distinct from this execution evidence. No external reviewer or hardware qualification is claimed.

The artwork faultlab-youtube-thumbnail.png was generated with the built-in image-generation tool. It is an abstract illustration, not a software screenshot or native-result evidence. report-synthetic-desktop.png is an actual browser capture of the generated report, visibly labeled synthetic. No corporate logo, music or third-party product screenshot is incorporated.

QNX is the platform targeted by the project; no affiliation, endorsement or safety certification is claimed. SDK use and redistribution remain governed by the applicable QNX licenses. Human experience, market demand, time savings and production suitability are unverified.
