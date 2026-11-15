1. read the AGENTS.md file, it contains the latest direction of the project. audit the project for places where diverges from the AGENTS file, especially the product list + provisioning parts, the UI, and the README.
1.1. handle any TODOs in AGENTS.md
2. check inot the anti-counterfeit integrity canary, document what it does and make an argument to keep or get rid of it
3. ditch these half-baked features, nuke them from repo:
                                                                                                                                     

 - Settlement hub (settlement_hub) — no dedicated module. Tier4 sells it, product_sku.json lists it as a hidden feature, but it      

   appears to be an umbrella over existing pieces (multi-GPU + distillation + LoRa gateway) rather than its own code. Treat as       

   roadmap/aspirational.

    - Interactive STEM practice tutor — the Khan curriculum engine provides structured lessons; "interactive practice" depth beyond     

   that isn't evidenced.                             (get rid of itneractive lession part, content should still be viewable)            


    - ESP32/LoRa thin-client mesh (lora_mesh_agent, mesh protocol) — partially implemented. mesh/esp32_protocol.py (414 lines) defines  

   serial/HTTP protocol contracts; packet_chunker.py is a 26-line stub; calculators expose format_mesh_summary() for ≤200B packets;  

   handle_mesh_command() exists in the server. No ESP32 hardware path is exercised by tests — best described as protocol-complete,   

   hardware-untested.

    - Survival calculators (survival_calculators) — implemented. Four calculators (water purification, solar/battery, medical           

   rehydration, electrical formulas) + calculators/source_audit.py auto-router, exposed via run_calculator().
