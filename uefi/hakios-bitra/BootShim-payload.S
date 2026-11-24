/* Mu-Silicium BootShim for bitra, plus: copy the XNUP payload that follows the UEFI FD to PAYLOAD_BASE.
 * Layout of the (decompressed) kernel image: [this shim][UEFI FD, FD_SIZE bytes][payload, PAYLOAD_SIZE bytes]. */
_Head:
  adr   x1, _Payload
  b     _Start

_StackBase:
  .quad FD_BASE
_StackSize:
  .quad IMAGE_SIZE      /* the whole image (shim + FD + payload): ABL places the DTB and ramdisk after it */
  .quad 0
  .quad 0
  .quad 0
  .quad 0
  .ascii "ARM\x64"
  .long 0

_Start:
  mov   x4, x1
  ldr   x5, =FD_BASE
  ldr   x6, =FD_SIZE
  add   x7, x1, x6          /* payload source: right after the FD */
  cmp   x4, x5
  beq   _CopyPayload
_CopyLoop:
  ldp   x2, x3, [x4], #16
  stp   x2, x3, [x5], #16
  subs  x6, x6, #16
  b.ne  _CopyLoop

_CopyPayload:
  /* Not a copy: with the MMU off a 15 MB copy never finished (the phone stayed on the fastboot logo, tests of
   * 2026-11-24). Leave a mailbox in the FD's unused tail instead: the loader copies the payload with the caches on. */
  ldr   x8, =(FD_BASE + FD_SIZE - 0x1000)
  ldr   x9, =MAILBOX_MAGIC
  stp   x9, x7, [x8]
  ldr   x9, =PAYLOAD_SIZE
  str   x9, [x8, #16]

_Entry:
  ldr   x5, =FD_BASE
  br    x5

_Dead:
  b     _Dead

.ltorg                    /* literals go here, before _Payload (else the FD would be read from the pool) */
.text
.align 4

_Payload:
