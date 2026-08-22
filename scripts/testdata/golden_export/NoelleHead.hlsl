struct vb0 { float3 position; float3 normal; float4 tangent; };
RWStructuredBuffer<vb0> rw_buffer : register(u1);
StructuredBuffer<vb0> base : register(t0);
StructuredBuffer<vb0> key : register(t1);
#define HS_EPS 1e-4
[numthreads(1, 1, 1)]
void main(uint3 DTid : SV_DispatchThreadID) {
    // Idempotent: sections sharing one bind hash must not stack deltas.
    float3 cur = rw_buffer[DTid.x].position;
    float3 b = base[DTid.x].position;
    float3 k = key[DTid.x].position;
    if (distance(cur, k) < HS_EPS) return;
    if (distance(cur, b) < HS_EPS)
        rw_buffer[DTid.x].position = k;
}
