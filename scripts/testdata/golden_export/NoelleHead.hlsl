struct vb0 { float3 position; float3 normal; float4 tangent; };
RWStructuredBuffer<vb0> rw_buffer : register(u1);
StructuredBuffer<vb0> base : register(t0);
StructuredBuffer<vb0> key : register(t1);
[numthreads(1, 1, 1)]
void main(uint3 DTid : SV_DispatchThreadID) {
    rw_buffer[DTid.x].position += key[DTid.x].position - base[DTid.x].position;
}
